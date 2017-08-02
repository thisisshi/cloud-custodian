# Copyright 2016 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import, division, print_function, unicode_literals

import itertools
import operator
import random
import re

import six
from botocore.exceptions import ClientError
from dateutil.parser import parse
from concurrent.futures import as_completed

from c7n.actions import (
    ActionRegistry, BaseAction, AutoTagUser, ModifyVpcSecurityGroupsAction
)
from c7n.filters import (
    FilterRegistry, AgeFilter, ValueFilter, Filter, OPERATORS, DefaultVpcBase
)
from c7n.filters.offhours import OffHour, OnHour
from c7n.filters.health import HealthEventFilter
import c7n.filters.vpc as net_filters

from c7n.manager import resources
from c7n.query import QueryResourceManager

from c7n import utils
from c7n.utils import type_schema


filters = FilterRegistry('ec2.filters')
actions = ActionRegistry('ec2.actions')

actions.register('auto-tag-user', AutoTagUser)
filters.register('health-event', HealthEventFilter)


@resources.register('ec2')
class EC2(QueryResourceManager):

    class resource_type(object):
        service = 'ec2'
        type = 'instance'
        enum_spec = ('describe_instances', 'Reservations[].Instances[]', None)
        detail_spec = None
        id = 'InstanceId'
        filter_name = 'InstanceIds'
        filter_type = 'list'
        name = 'PublicDnsName'
        date = 'LaunchTime'
        dimension = 'InstanceId'
        config_type = "AWS::EC2::Instance"
        shape = "Instance"

        default_report_fields = (
            'CustodianDate',
            'InstanceId',
            'tag:Name',
            'InstanceType',
            'LaunchTime',
            'VpcId',
            'PrivateIpAddress',
        )

    filter_registry = filters
    action_registry = actions

    # if we have to do a fallback scenario where tags don't come in describe
    permissions = ('ec2:DescribeTags',)

    def __init__(self, ctx, data):
        super(EC2, self).__init__(ctx, data)
        self.queries = QueryFilter.parse(self.data.get('query', []))

    def resources(self, query=None):
        q = self.resource_query()
        if q is not None:
            query = query or {}
            query['Filters'] = q
        return super(EC2, self).resources(query=query)

    def resource_query(self):
        qf = []
        qf_names = set()
        # allow same name to be specified multiple times and append the queries
        # under the same name
        for q in self.queries:
            qd = q.query()
            if qd['Name'] in qf_names:
                for qf in qf:
                    if qd['Name'] == qf['Name']:
                        qf['Values'].extend(qd['Values'])
            else:
                qf_names.add(qd['Name'])
                qf.append(qd)
        return qf

    def augment(self, resources):
        """EC2 API and AWOL Tags

        While ec2 api generally returns tags when doing describe_x on for
        various resources, it may also silently fail to do so unless a tag
        is used as a filter.

        See footnote on http://goo.gl/YozD9Q for official documentation.

        Apriori we may be using custodian to ensure tags (including
        name), so there isn't a good default to ensure that we will
        always get tags from describe_x calls.
        """

        # First if we're in event based lambda go ahead and skip this,
        # tags can't be trusted in ec2 instances immediately post creation.
        if not resources or self.data.get('mode', {}).get('type', '') in (
                'cloudtrail', 'ec2-instance-state'):
            return resources

        # AWOL detector, so we don't make extraneous api calls.
        resource_count = len(resources)
        search_count = min(int(resource_count % 0.05) + 1, 5)
        if search_count > resource_count:
            search_count = resource_count
        found = False
        for r in random.sample(resources, search_count):
            if 'Tags' in r:
                found = True
                break

        if found:
            return resources

        # Okay go and do the tag lookup
        client = utils.local_session(self.session_factory).client('ec2')
        tag_set = self.retry(
            client.describe_tags,
            Filters=[{'Name': 'resource-type',
                      'Values': ['instance']}])['Tags']
        resource_tags = {}
        for t in tag_set:
            t.pop('ResourceType')
            rid = t.pop('ResourceId')
            resource_tags.setdefault(rid, []).append(t)

        m = self.get_model()
        for r in resources:
            r['Tags'] = resource_tags.get(r[m.id], ())
        return resources


@filters.register('security-group')
class SecurityGroupFilter(net_filters.SecurityGroupFilter):

    RelatedIdsExpression = "SecurityGroups[].GroupId"


@filters.register('subnet')
class SubnetFilter(net_filters.SubnetFilter):

    RelatedIdsExpression = "SubnetId"


filters.register('network-location', net_filters.NetworkLocation)


@filters.register('state-age')
class StateTransitionAge(AgeFilter):
    """Age an instance has been in the given state.

    .. code-block: yaml

        policies:
          - name: ec2-state-running-7-days
            resource: ec2
            filters:
              - type: state-age
                op: ge
                days: 7
    """
    RE_PARSE_AGE = re.compile("\(.*?\)")

    # this filter doesn't use date_attribute, but needs to define it
    # to pass AgeFilter's validate method
    date_attribute = "dummy"

    schema = type_schema(
        'state-age',
        op={'type': 'string', 'enum': list(OPERATORS.keys())},
        days={'type': 'number'})

    def get_resource_date(self, i):
        v = i.get('StateTransitionReason')
        if not v:
            return None
        dates = self.RE_PARSE_AGE.findall(v)
        if dates:
            return parse(dates[0][1:-1])
        return None


class StateTransitionFilter(object):
    """Filter instances by state.

    Try to simplify construction for policy authors by automatically
    filtering elements (filters or actions) to the instances states
    they are valid for.

    For more details see http://goo.gl/TZH9Q5
    """
    valid_origin_states = ()

    def filter_instance_state(self, instances, states=None):
        states = states or self.valid_origin_states
        orig_length = len(instances)
        results = [i for i in instances
                   if i['State']['Name'] in states]
        self.log.info("%s %d of %d instances" % (
            self.__class__.__name__, len(results), orig_length))
        return results


@filters.register('ebs')
class AttachedVolume(ValueFilter):
    """EC2 instances with EBS backed volume

    Filters EC2 instances with EBS backed storage devices (non ephemeral)

    :Example:

    .. code-block:: yaml

        policies:
          - name: ec2-encrypted-ebs-volumes
            resource: ec2
            filters:
              - type: ebs
                key: encrypted
                value: true
    """

    schema = type_schema(
        'ebs', rinherit=ValueFilter.schema,
        **{'operator': {'enum': ['and', 'or']},
           'skip-devices': {'type': 'array', 'items': {'type': 'string'}}})

    def get_permissions(self):
        return self.manager.get_resource_manager('ebs').get_permissions()

    def process(self, resources, event=None):
        self.volume_map = self.get_volume_mapping(resources)
        self.skip = self.data.get('skip-devices', [])
        self.operator = self.data.get(
            'operator', 'or') == 'or' and any or all
        return list(filter(self, resources))

    def get_volume_mapping(self, resources):
        volume_map = {}
        manager = self.manager.get_resource_manager('ebs')
        for instance_set in utils.chunks(resources, 200):
            volume_ids = []
            for i in instance_set:
                for bd in i.get('BlockDeviceMappings', ()):
                    if 'Ebs' not in bd:
                        continue
                    volume_ids.append(bd['Ebs']['VolumeId'])
            for v in manager.get_resources(volume_ids):
                if not v['Attachments']:
                    continue
                volume_map.setdefault(
                    v['Attachments'][0]['InstanceId'], []).append(v)
        return volume_map

    def __call__(self, i):
        volumes = self.volume_map.get(i['InstanceId'])
        if not volumes:
            return False
        if self.skip:
            for v in list(volumes):
                for a in v.get('Attachments', []):
                    if a['Device'] in self.skip:
                        volumes.remove(v)
        return self.operator(map(self.match, volumes))


class InstanceImageBase(object):

    def get_image_mapping(self, resources):
        return {i['ImageId']: i for i in
                self.manager.get_resource_manager('ami').resources()}


@filters.register('image-age')
class ImageAge(AgeFilter, InstanceImageBase):
    """EC2 AMI age filter

    Filters EC2 instances based on the age of their AMI image (in days)

    :Example:

    .. code-block: yaml

        policies:
          - name: ec2-ancient-ami
            resource: ec2
            filters:
              - type: image-age
                op: ge
                days: 90
    """

    date_attribute = "CreationDate"

    schema = type_schema(
        'image-age',
        op={'type': 'string', 'enum': list(OPERATORS.keys())},
        days={'type': 'number'})

    def get_permissions(self):
        return self.manager.get_resource_manager('ami').get_permissions()

    def process(self, resources, event=None):
        self.image_map = self.get_image_mapping(resources)
        return super(ImageAge, self).process(resources, event)

    def get_resource_date(self, i):
        if i['ImageId'] not in self.image_map:
            # our image is no longer available
            return parse("2000-01-01T01:01:01.000Z")
        image = self.image_map[i['ImageId']]
        return parse(image['CreationDate'])


@filters.register('image')
class InstanceImage(ValueFilter, InstanceImageBase):

    schema = type_schema('image', rinherit=ValueFilter.schema)

    def get_permissions(self):
        return self.manager.get_resource_manager('ami').get_permissions()

    def process(self, resources, event=None):
        self.image_map = self.get_image_mapping(resources)
        return super(InstanceImage, self).process(resources, event)

    def __call__(self, i):
        image = self.image_map.get(i['ImageId'])
        if not image:
            self.log.warning(
                "Could not locate image for instance:%s ami:%s" % (
                    i['InstanceId'], i["ImageId"]))
            # Match instead on empty skeleton?
            return False
        return self.match(image)


@filters.register('offhour')
class InstanceOffHour(OffHour, StateTransitionFilter):
    """Custodian OffHour filter

    Filters running EC2 instances with the intent to stop at a given hour of
    the day.

    :Example:

    .. code-block: yaml

        policies:
          - name: onhour-evening-stop
            resource: ec2
            filters:
              - type: offhour
                tag: custodian_downtime
                default_tz: et
                offhour: 20
            actions:
              - stop
    """

    valid_origin_states = ('running',)

    def process(self, resources, event=None):
        return super(InstanceOffHour, self).process(
            self.filter_instance_state(resources))


@filters.register('onhour')
class InstanceOnHour(OnHour, StateTransitionFilter):
    """Custodian OnHour filter

    Filters stopped EC2 instances with the intent to start at a given hour of
    the day.

    :Example:

    .. code-block: yaml

        policies:
          - name: onhour-morning-start
            resource: ec2
            filters:
              - type: onhour
                tag: custodian_downtime
                default_tz: et
                onhour: 6
            actions:
              - start
    """

    valid_origin_states = ('stopped',)

    def process(self, resources, event=None):
        return super(InstanceOnHour, self).process(
            self.filter_instance_state(resources))


@filters.register('ephemeral')
class EphemeralInstanceFilter(Filter):
    """EC2 instances with ephemeral storage

    Filters EC2 instances that have ephemeral storage (an instance-store backed
    root device)

    :Example:

    .. code-block: yaml

        policies:
          - name: ec2-ephemeral-instances
            resource: ec2
            filters:
              - type: ephemeral

    http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/InstanceStorage.html
    """

    schema = type_schema('ephemeral')

    def __call__(self, i):
        return self.is_ephemeral(i)

    @staticmethod
    def is_ephemeral(i):
        for bd in i.get('BlockDeviceMappings', []):
            if bd['DeviceName'] in ('/dev/sda1', '/dev/xvda'):
                if 'Ebs' in bd:
                    return False
                return True
        return True


@filters.register('instance-uptime')
class UpTimeFilter(AgeFilter):

    date_attribute = "LaunchTime"

    schema = type_schema(
        'instance-uptime',
        op={'type': 'string', 'enum': list(OPERATORS.keys())},
        days={'type': 'number'})


@filters.register('instance-age')
class InstanceAgeFilter(AgeFilter):
    """Filters instances based on their age (in days)

    :Example:

    .. code-block: yaml

        policies:
          - name: ec2-30-days-plus
            resource: ec2
            filters:
              - type: instance-age
                op: ge
                days: 30
    """

    date_attribute = "LaunchTime"
    ebs_key_func = operator.itemgetter('AttachTime')

    schema = type_schema(
        'instance-age',
        op={'type': 'string', 'enum': list(OPERATORS.keys())},
        days={'type': 'number'},
        hours={'type': 'number'},
        minutes={'type': 'number'})

    def get_resource_date(self, i):
        # LaunchTime is basically how long has the instance
        # been on, use the oldest ebs vol attach time
        ebs_vols = [
            block['Ebs'] for block in i['BlockDeviceMappings']
            if 'Ebs' in block]
        if not ebs_vols:
            # Fall back to using age attribute (ephemeral instances)
            return super(InstanceAgeFilter, self).get_resource_date(i)
        # Lexographical sort on date
        ebs_vols = sorted(ebs_vols, key=self.ebs_key_func)
        return ebs_vols[0]['AttachTime']


@filters.register('default-vpc')
class DefaultVpc(DefaultVpcBase):
    """ Matches if an ec2 database is in the default vpc
    """

    schema = type_schema('default-vpc')

    def __call__(self, ec2):
        return ec2.get('VpcId') and self.match(ec2.get('VpcId')) or False


@filters.register('singleton')
class SingletonFilter(Filter, StateTransitionFilter):
    """EC2 instances without autoscaling or a recover alarm

    Filters EC2 instances that are not members of an autoscaling group
    and do not have Cloudwatch recover alarms.

    :Example:

    .. code-block: yaml

        policies:
          - name: ec2-recover-instances
            resource: ec2
            filters:
              - singleton
            actions:
              - type: tag
                key: problem
                value: instance is not resilient

    https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-recover.html
    """

    schema = type_schema('singleton')

    permissions = ('cloudwatch:DescribeAlarmsForMetric',)

    valid_origin_states = ('running', 'stopped', 'pending', 'stopping')

    in_asg = ValueFilter({
        'key': 'tag:aws:autoscaling:groupName',
        'value': 'not-null'}).validate()

    def process(self, instances, event=None):
        return super(SingletonFilter, self).process(
            self.filter_instance_state(instances))

    def __call__(self, i):
        if self.in_asg(i):
            return False
        else:
            return not self.has_recover_alarm(i)

    def has_recover_alarm(self, i):
        client = utils.local_session(self.manager.session_factory).client('cloudwatch')
        alarms = client.describe_alarms_for_metric(
            MetricName='StatusCheckFailed_System',
            Namespace='AWS/EC2',
            Dimensions=[
                {
                    'Name': 'InstanceId',
                    'Value': i['InstanceId']
                }
            ]
        )

        for i in alarms['MetricAlarms']:
            for a in i['AlarmActions']:
                if (
                    a.startswith('arn:aws:automate:') and
                    a.endswith(':ec2:recover')
                ):
                    return True

        return False


@actions.register('start')
class Start(BaseAction, StateTransitionFilter):
    """Starts a previously stopped EC2 instance.

    :Example:

    .. code-block: yaml

        policies:
          - name: ec2-start-stopped-instances
            resource: ec2
            query:
              - instance-state-name: stopped
            actions:
              - start

    http://docs.aws.amazon.com/cli/latest/reference/ec2/start-instances.html
    """

    valid_origin_states = ('stopped',)
    schema = type_schema('start')
    permissions = ('ec2:StartInstances',)
    batch_size = 10

    def _filter_ec2_with_volumes(self, instances):
        return [i for i in instances if len(i['BlockDeviceMappings']) > 0]

    def process(self, instances):
        instances = self._filter_ec2_with_volumes(
            self.filter_instance_state(instances))
        if not len(instances):
            return

        client = utils.local_session(
            self.manager.session_factory).client('ec2')

        # Play nice around aws having insufficient capacity...
        for itype, t_instances in utils.group_by(
                instances, 'InstanceType').items():
            for izone, z_instances in utils.group_by(
                    t_instances, 'AvailabilityZone').items():
                for batch in utils.chunks(z_instances, self.batch_size):
                    self.process_instance_set(client, batch, itype, izone)

    def process_instance_set(self, client, instances, itype, izone):
        # Setup retry with insufficient capacity as well
        retry = utils.get_retry((
            'InsufficientInstanceCapacity',
            'RequestLimitExceeded', 'Client.RequestLimitExceeded'),
            max_attempts=5)
        instance_ids = [i['InstanceId'] for i in instances]
        try:
            retry(client.start_instances, InstanceIds=instance_ids)
        except ClientError as e:
            if e.response['Error']['Code'] == 'InsufficientInstanceCapacity':
                self.log.exception(
                    ("Could not start instances:%d type:%s"
                     " zone:%s instances:%s error:%s"),
                    len(instances), itype, izone,
                    ", ".join(instance_ids), e)
                return
            self.log.exception("Error while starting instances error %s", e)
            raise


@actions.register('resize')
class Resize(BaseAction, StateTransitionFilter):
    """Change an instance's size.

    An instance can only be resized when its stopped, this action
    can optionally restart an instance if needed to effect the instance
    type change. Instances are always left in the run state they were
    found in.

    There are a few caveats to be aware of, instance resizing
    needs to maintain compatibility for architecture, virtualization type
    hvm/pv, and ebs optimization at minimum.

    http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-resize.html
    """

    schema = type_schema(
        'resize',
        **{'restart': {'type': 'boolean'},
           'type-map': {'type': 'object'},
           'default': {'type': 'string'}})

    valid_origin_states = ('running', 'stopped')

    def get_permissions(self):
        perms = ('ec2:DescribeInstances', 'ec2:ModifyInstanceAttribute')
        if self.data.get('restart', False):
            perms += ('ec2:StopInstances', 'ec2:StartInstances')
        return perms

    def process(self, resources):
        stopped_instances = self.filter_instance_state(
            resources, ('stopped',))
        running_instances = self.filter_instance_state(
            resources, ('running',))

        if self.data.get('restart') and running_instances:
            Stop({'terminate-ephemeral': False},
                 self.manager).process(running_instances)
            client = utils.local_session(
                self.manager.session_factory).client('ec2')
            waiter = client.get_waiter('instance_stopped')
            try:
                waiter.wait(
                    InstanceIds=[r['InstanceId'] for r in running_instances])
            except ClientError as e:
                self.log.exception(
                    "Exception stopping instances for resize:\n %s" % e)

        for instance_set in utils.chunks(itertools.chain(
                stopped_instances, running_instances), 20):
            self.process_resource_set(instance_set)

        if self.data.get('restart') and running_instances:
            client.start_instances(
                InstanceIds=[i['InstanceId'] for i in running_instances])
        return list(itertools.chain(stopped_instances, running_instances))

    def process_resource_set(self, instance_set):
        type_map = self.data.get('type-map')
        default_type = self.data.get('default')

        client = utils.local_session(
            self.manager.session_factory).client('ec2')

        for i in instance_set:
            self.log.debug(
                "resizing %s %s" % (i['InstanceId'], i['InstanceType']))
            new_type = type_map.get(i['InstanceType'], default_type)
            if new_type == i['InstanceType']:
                continue
            try:
                client.modify_instance_attribute(
                    InstanceId=i['InstanceId'],
                    InstanceType={'Value': new_type})
            except ClientError as e:
                self.log.exception(
                    "Exception resizing instance:%s new:%s old:%s \n %s" % (
                        i['InstanceId'], new_type, i['InstanceType'], e))


@actions.register('stop')
class Stop(BaseAction, StateTransitionFilter):
    """Stops a running EC2 instances

    :Example:

    .. code-block: yaml

        policies:
          - name: ec2-stop-running-instances
            resource: ec2
            query:
              - instance-state-name: running
            actions:
              - stop
    """
    valid_origin_states = ('running',)

    schema = type_schema('stop', **{'terminate-ephemeral': {'type': 'boolean'}})

    def get_permissions(self):
        perms = ('ec2:StopInstances',)
        if self.data.get('terminate-ephemeral', False):
            perms += ('ec2:TerminateInstances',)
        return perms

    def split_on_storage(self, instances):
        ephemeral = []
        persistent = []
        for i in instances:
            if EphemeralInstanceFilter.is_ephemeral(i):
                ephemeral.append(i)
            else:
                persistent.append(i)
        return ephemeral, persistent

    def process(self, instances):
        instances = self.filter_instance_state(instances)
        if not len(instances):
            return
        client = utils.local_session(
            self.manager.session_factory).client('ec2')
        # Ephemeral instance can't be stopped.
        ephemeral, persistent = self.split_on_storage(instances)
        if self.data.get('terminate-ephemeral', False) and ephemeral:
            self._run_instances_op(
                client.terminate_instances,
                [i['InstanceId'] for i in ephemeral])
        if persistent:
            self._run_instances_op(
                client.stop_instances,
                [i['InstanceId'] for i in persistent])
        return instances

    def _run_instances_op(self, op, instance_ids):
        while True:
            try:
                return self.manager.retry(op, InstanceIds=instance_ids)
            except ClientError as e:
                if e.response['Error']['Code'] == 'IncorrectInstanceState':
                    msg = e.response['Error']['Message']
                    e_instance_id = msg[msg.find("'") + 1:msg.rfind("'")]
                    instance_ids.remove(e_instance_id)
                    if not instance_ids:
                        return
                    continue
                raise


@actions.register('terminate')
class Terminate(BaseAction, StateTransitionFilter):
    """ Terminate a set of instances.

    While ec2 offers a bulk delete api, any given instance can be configured
    with api deletion termination protection, so we can't use the bulk call
    reliabily, we need to process the instances individually. Additionally
    If we're configured with 'force' then we'll turn off instance termination
    protection.

    :Example:

    .. code-block: yaml

        policies:
          - name: ec2-process-termination
            resource: ec2
            filters:
              - type: marked-for-op
                op: terminate
            actions:
              - terminate
    """

    valid_origin_states = ('running', 'stopped', 'pending', 'stopping')

    schema = type_schema('terminate', force={'type': 'boolean'})

    def get_permissions(self):
        permissions = ("ec2:TerminateInstances",)
        if self.data.get('force'):
            permissions += ('ec2:ModifyInstanceAttribute',)
        return permissions

    def process(self, instances):
        instances = self.filter_instance_state(instances)
        if not len(instances):
            return
        if self.data.get('force'):
            self.log.info("Disabling termination protection on instances")
            self.disable_deletion_protection(instances)
        client = utils.local_session(
            self.manager.session_factory).client('ec2')
        # limit batch sizes to avoid api limits
        for batch in utils.chunks(instances, 100):
            self.manager.retry(
                client.terminate_instances,
                InstanceIds=[i['InstanceId'] for i in instances])

    def disable_deletion_protection(self, instances):

        @utils.worker
        def process_instance(i):
            client = utils.local_session(
                self.manager.session_factory).client('ec2')
            try:
                self.manager.retry(
                    client.modify_instance_attribute,
                    InstanceId=i['InstanceId'],
                    Attribute='disableApiTermination',
                    Value='false')
            except ClientError as e:
                if e.response['Error']['Code'] == 'IncorrectInstanceState':
                    return
                raise

        with self.executor_factory(max_workers=2) as w:
            list(w.map(process_instance, instances))


@actions.register('snapshot')
class Snapshot(BaseAction):
    """Snapshots volumes attached to an EC2 instance

    :Example:

    .. code-block: yaml

        policies:
          - name: ec2-snapshots
            resource: ec2
          actions:
            - type: snapshot
              copy-tags:
                - Name
    """

    schema = type_schema(
        'snapshot',
        **{'copy-tags': {'type': 'array', 'items': {'type': 'string'}}})
    permissions = ('ec2:CreateSnapshot', 'ec2:CreateTags',)

    def process(self, resources):
        for resource in resources:
            with self.executor_factory(max_workers=2) as w:
                futures = []
                futures.append(w.submit(self.process_volume_set, resource))
                for f in as_completed(futures):
                    if f.exception():
                        self.log.error(
                            "Exception creating snapshot set \n %s" % (
                                f.exception()))

    @utils.worker
    def process_volume_set(self, resource):
        c = utils.local_session(self.manager.session_factory).client('ec2')
        for block_device in resource['BlockDeviceMappings']:
            if 'Ebs' not in block_device:
                continue
            volume_id = block_device['Ebs']['VolumeId']
            description = "Automated,Backup,%s,%s" % (
                resource['InstanceId'],
                volume_id)
            try:
                response = c.create_snapshot(
                    DryRun=self.manager.config.dryrun,
                    VolumeId=volume_id,
                    Description=description)
            except ClientError as e:
                if e.response['Error']['Code'] == 'IncorrectState':
                    self.log.warning(
                        "action:%s volume:%s is incorrect state" % (
                            self.__class__.__name__.lower(),
                            volume_id))
                    continue
                raise

            tags = [
                {'Key': 'Name', 'Value': volume_id},
                {'Key': 'InstanceId', 'Value': resource['InstanceId']},
                {'Key': 'DeviceName', 'Value': block_device['DeviceName']},
                {'Key': 'custodian_snapshot', 'Value': ''}
            ]

            copy_keys = self.data.get('copy-tags', [])
            copy_tags = []
            if copy_keys:
                for t in resource.get('Tags', []):
                    if t['Key'] in copy_keys:
                        copy_tags.append(t)

            if len(copy_tags) + len(tags) > 40:
                self.log.warning(
                    "action:%s volume:%s too many tags to copy" % (
                        self.__class__.__name__.lower(),
                        volume_id))
                copy_tags = []

            tags.extend(copy_tags)
            c.create_tags(
                DryRun=self.manager.config.dryrun,
                Resources=[
                    response['SnapshotId']],
                Tags=tags)


@actions.register('modify-security-groups')
class EC2ModifyVpcSecurityGroups(ModifyVpcSecurityGroupsAction):
    """Modify security groups on an instance."""

    permissions = ("ec2:ModifyNetworkInterfaceAttribute",)

    def process(self, instances):
        if not len(instances):
            return
        client = utils.local_session(
            self.manager.session_factory).client('ec2')

        # handle multiple ENIs
        interfaces = []
        for i in instances:
            for eni in i['NetworkInterfaces']:
                if i.get('c7n.matched-security-groups'):
                    eni['c7n.matched-security-groups'] = i[
                        'c7n.matched-security-groups']
                interfaces.append(eni)

        groups = super(EC2ModifyVpcSecurityGroups, self).get_groups(interfaces)

        for idx, i in enumerate(interfaces):
            client.modify_network_interface_attribute(
                NetworkInterfaceId=i['NetworkInterfaceId'],
                Groups=groups[idx])


@actions.register('autorecover-alarm')
class AutorecoverAlarm(BaseAction, StateTransitionFilter):
    """Adds a cloudwatch metric alarm to recover an EC2 instance.

    This action takes effect on instances that are NOT part
    of an ASG.

    :Example:

    .. code-block: yaml

        policies:
          - name: ec2-autorecover-alarm
            resource: ec2
            filters:
              - singleton
          actions:
            - autorecover-alarm

    https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-recover.html
    """

    schema = type_schema('autorecover-alarm')
    permissions = ('ec2:DescribeInstanceStatus',
                   'ec2:RecoverInstances',
                   'ec2:DescribeInstanceRecoveryAttribute')

    valid_origin_states = ('running', 'stopped', 'pending', 'stopping')
    filter_asg_membership = ValueFilter({
        'key': 'tag:aws:autoscaling:groupName',
        'value': 'empty'}).validate()

    def process(self, instances):
        instances = self.filter_asg_membership.process(
            self.filter_instance_state(instances))
        if not len(instances):
            return
        client = utils.local_session(
            self.manager.session_factory).client('cloudwatch')
        for i in instances:
            client.put_metric_alarm(
                AlarmName='recover-{}'.format(i['InstanceId']),
                AlarmDescription='Auto Recover {}'.format(i['InstanceId']),
                ActionsEnabled=True,
                AlarmActions=[
                    'arn:aws:automate:{}:ec2:recover'.format(
                        i['Placement']['AvailabilityZone'][:-1])
                ],
                MetricName='StatusCheckFailed_System',
                Namespace='AWS/EC2',
                Statistic='Minimum',
                Dimensions=[
                    {
                        'Name': 'InstanceId',
                        'Value': i['InstanceId']
                    }
                ],
                Period=60,
                EvaluationPeriods=2,
                Threshold=0,
                ComparisonOperator='GreaterThanThreshold'
            )


@actions.register('set-instance-profile')
class SetInstanceProfile(BaseAction, StateTransitionFilter):
    """Sets (or removes) the instance profile for a running EC2 instance.

    :Example:

    .. code-block: yaml

        policies:
          - name: set-default-instance-profile
            resource: ec2
            query:
              - IamInstanceProfile: absent
            actions:
              - type: set-instance-profile
                name: default

    https://docs.aws.amazon.com/cli/latest/reference/ec2/associate-iam-instance-profile.html
    https://docs.aws.amazon.com/cli/latest/reference/ec2/disassociate-iam-instance-profile.html
    """

    schema = type_schema(
        'set-instance-profile',
        **{'name': {'type': 'string'}})

    permissions = (
        'ec2:AssociateIamInstanceProfile',
        'ec2:DisassociateIamInstanceProfile',
        'iam:PassRole')

    valid_origin_states = ('running', 'pending')

    def process(self, instances):
        instances = self.filter_instance_state(instances)
        if not len(instances):
            return
        client = utils.local_session(
            self.manager.session_factory).client('ec2')
        profile_name = self.data.get('name', '')

        for i in instances:
            if profile_name:
                client.associate_iam_instance_profile(
                    IamInstanceProfile={'Name': self.data.get('name', '')},
                    InstanceId=i['InstanceId'])
            else:
                response = client.describe_iam_instance_profile_associations(
                    Filters=[
                        {
                            'Name': 'instance-id',
                            'Values': [i['InstanceId']],
                        },
                        {
                            'Name': 'state',
                            'Values': ['associating', 'associated']
                        }
                    ]
                )
                for a in response['IamInstanceProfileAssociations']:
                    client.disassociate_iam_instance_profile(
                        AssociationId=a['AssociationId']
                    )

        return instances


# Valid EC2 Query Filters
# http://docs.aws.amazon.com/AWSEC2/latest/CommandLineReference/ApiReference-cmd-DescribeInstances.html
EC2_VALID_FILTERS = {
    'architecture': ('i386', 'x86_64'),
    'availability-zone': str,
    'iam-instance-profile.arn': str,
    'image-id': str,
    'instance-id': str,
    'instance-lifecycle': ('spot',),
    'instance-state-name': (
        'pending',
        'terminated',
        'running',
        'shutting-down',
        'stopping',
        'stopped'),
    'instance.group-id': str,
    'instance.group-name': str,
    'tag-key': str,
    'tag-value': str,
    'tag:': str,
    'vpc-id': str}


class QueryFilter(object):

    @classmethod
    def parse(cls, data):
        results = []
        for d in data:
            if not isinstance(d, dict):
                raise ValueError(
                    "EC2 Query Filter Invalid structure %s" % d)
            results.append(cls(d).validate())
        return results

    def __init__(self, data):
        self.data = data
        self.key = None
        self.value = None

    def validate(self):
        if not len(list(self.data.keys())) == 1:
            raise ValueError(
                "EC2 Query Filter Invalid %s" % self.data)
        self.key = list(self.data.keys())[0]
        self.value = list(self.data.values())[0]

        if self.key not in EC2_VALID_FILTERS and not self.key.startswith(
                'tag:'):
            raise ValueError(
                "EC2 Query Filter invalid filter name %s" % (self.data))

        if self.value is None:
            raise ValueError(
                "EC2 Query Filters must have a value, use tag-key"
                " w/ tag name as value for tag present checks"
                " %s" % self.data)
        return self

    def query(self):
        value = self.value
        if isinstance(self.value, six.string_types):
            value = [self.value]

        return {'Name': self.key, 'Values': value}
