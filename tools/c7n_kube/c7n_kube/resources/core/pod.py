# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
from c7n_kube.query import QueryResourceManager, TypeInfo
from c7n_kube.provider import resources
from c7n_kube.resources.apps.deployment import EventEnsureRegistryAction


@resources.register('pod')
class Pod(QueryResourceManager):

    class resource_type(TypeInfo):
        group = 'Core'
        version = 'V1'
        patch = 'patch_namespaced_pod'
        delete = 'delete_namespaced_pod'
        enum_spec = ('list_pod_for_all_namespaces', 'items', None)
        plural = 'pods'


@Pod.action_registry.register('event-ensure-registry')
class EventEnsureRegistryAction(EventEnsureRegistryAction):
    def get_containers(self, resource):
        return resource['spec']['containers']

    def get_init_containers(self, resource):
        return resource['spec']['initContainers']
