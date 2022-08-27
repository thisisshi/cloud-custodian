# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging

from c7n.policy import PolicyExecutionMode, execution
from c7n.utils import type_schema, dumps


log = logging.getLogger('custodian.k8s.policy')


class K8sEventMode(PolicyExecutionMode):
    pass


@execution.register('k8s-validator')
class ValidatingControllerMode(K8sEventMode):
    """
    Validating Admission Controller Mode

    Actions are not compatible with Validating Admission Controller Mode

    Define operations to monitor:

    operations:
      - CREATE
      - UPDATE

    Include a description to provide a message on failure:

    .. example::

      policies:
        - name: 'require-only-label-foo'
          resource: 'k8s.deployment'
          description: 'All deployments must only have label:foo'
          mode:
            type: k8s-validator
            on-match: deny
            operations:
            - CREATE
          filters:
            - type: value
              key: keys(metadata.labels)
              value: ['foo']
              op: ne
    """

    schema = type_schema(
        'k8s-validator',
        required=['operations'],
        **{
            'on-match': {'enum': ['allow', 'deny', 'warn']},
            'operations': {
                'type': 'array',
                'items': {
                    'enum': ['CREATE', 'UPDATE', 'DELETE', 'CONNECT']
                }
            }
        }
    )

    def _handle_scope(self, request, value):
        if request.get('namespace') and value == 'Namespaced':
            return True
        elif request.get('namespace') and value == 'Cluster':
            return False
        elif not request.get('namespace') and value == 'Cluster':
            return True
        return False

    def _handle_group(self, request, value):
        group = request['resource']['group']
        if group == '' and 'core' in value:
            return True
        return group == value

    def _handle_resources(self, request, value):
        resource = request['resource']['resource']
        return resource == value

    def _handle_api_versions(self, request, value):
        version = request['resource']['version']
        return version == value

    def _handle_operations(self, request, value):
        if '*' in value:
            return True
        return request['operation'] in value

    handlers = {
        'scope': _handle_scope,
        'group': _handle_group,
        'resources': _handle_resources,
        'apiVersions': _handle_api_versions,
        'operations': _handle_operations,
    }

    def get_match_values(self):
        scope = None
        version = None
        group = None
        resources = None

        model = self.policy.resource_manager.get_model()
        mode = self.policy.data['mode']

        # custom resources have to be treated a bit differently
        crds = ('custom-namespaced-resource', 'custom-cluster-resource',)
        if self.policy.resource_manager.type in crds:
            query = self.policy.data['query'][0]
            version = query['version'].lower()
            group = query['group'].lower()
            resources = query['plural'].lower()
            scope = 'Cluster'
            if self.policy.resource_manager.type == 'custom-namespaced-resource':
                scope = 'Namespaced'
        else:
            # set default values based on our models
            resources = model.plural.lower()
            group = model.group.lower()
            version = model.version.lower()
            scope = 'Namespaced' if model.namespaced else 'Cluster'

        return {
            'operations': mode.get('operations'),
            'resources': resources,
            'group': group,
            'apiVersions': version,
            'scope': scope,
        }

    def _filter_event(self, request):
        match_ = self.get_match_values()
        log.info(f"Matching event against:{match_}")
        matched = []
        for k, v in match_.items():
            if not v:
                continue
            matched.append(self.handlers[k](self, request, v))
        return all(matched)

    def run_resource_set(self, event, resources):
        with self.policy.ctx as ctx:
            ctx.metrics.put_metric(
                'ResourceCount', len(resources), 'Count', Scope="Policy", buffer=False
            )

            if 'debug' in event:
                self.policy.log.info(
                    "Invoking actions %s", self.policy.resource_manager.actions
                )

            ctx.output.write_file('resources.json', dumps(resources, indent=2))
            # we dont run any actions for validating admission controllers
        return resources

    def run(self, event, _):
        action = self.policy.data['mode'].get('on-match', 'deny')

        if not self.policy.is_runnable(event):
            return True, []
        log.info(f"Got event:{event}")
        matched = self._filter_event(event['request'])
        if not matched:
            log.warning("Event not matched, skipping")
            return True, []
        log.info("Event Matched")

        resources = [event['request']['object']]
        # we want to inspect the thing getting deleted, not null
        if event['request']['operation'] == 'DELETE':
            resources = [event['request']['oldObject']]

        resources = self.policy.resource_manager.filter_resources(resources, event)
        resources = self.run_resource_set(event, resources)

        log.info(f"Filtered from 1 to {len(resources)} resource(s)")

        if action == 'allow' and resources:
            result = 'allow'
        elif action == 'allow' and not resources:
            result = 'deny'
        elif action == 'deny' and resources:
            result = 'deny'
        elif action == 'deny' and not resources:
            result = 'allow'
        elif action == 'warn' and resources:
            result = 'warn'
        elif action == 'warn' and not resources:
            result = 'allow'

        if result in ('allow', 'warn',):
            verb = 'allowing'
        else:
            verb = 'denying'

        log.info(f'{verb} admission because on-match:{action}, matched:{len(resources)}')

        return result, resources
