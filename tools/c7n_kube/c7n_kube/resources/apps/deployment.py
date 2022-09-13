# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import copy
import re

import jsonpatch

from c7n_kube.actions.core import EventAction
from c7n_kube.query import QueryResourceManager, TypeInfo
from c7n_kube.provider import resources

from c7n.utils import type_schema


@resources.register('deployment')
class Deployment(QueryResourceManager):

    class resource_type(TypeInfo):
        group = 'Apps'
        version = 'V1'
        patch = 'patch_namespaced_deployment'
        delete = 'delete_namespaced_deployment'
        enum_spec = ('list_deployment_for_all_namespaces', 'items', None)
        plural = 'deployments'


@Deployment.action_registry.register('event-ensure-registry')
class EventEnsureRegistryAction(EventAction):
    """
    Ensures that images on all containers

    .. code-block:: yaml

        policies:
            - name: ensure-image-registry
              resource: k8s.deployment
              mode:
                type: k8s-validator
                on-match: warn
                operations:
                  - CREATE
                  - UPDATE
              actions:
                - type: event-ensure-registry
                  registry: myregistry.com
    """

    schema = type_schema(
        'event-ensure-registry', registry={'type': 'string'}, required=['registry'])

    def get_containers(self, resource):
        return resource['spec']['template']['spec']['containers']

    def get_init_containers(self, resource):
        return resource['spec']['template']['spec'].get('initContainers', [])

    def process(self, resources, event):
        prefix_match = re.compile(r'^[^/]+')
        for resource in resources:
            src = copy.deepcopy(resource)
            dst = copy.deepcopy(src)
            containers = self.get_containers(dst)
            init_containers = self.get_init_containers(dst)
            containers.extend(init_containers)
            for container in containers:
                if '/' not in container['image']:
                    container['image'] = '/'.join([self.data['registry'], container['image']])
                else:
                    container['image'] = prefix_match.sub(self.data['registry'], container['image'])
            patch = jsonpatch.make_patch(src, dst)
            resource.setdefault('c7n:patches', []).extend(patch.patch)
