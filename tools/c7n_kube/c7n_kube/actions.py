# Copyright 2018 Capital One Services, LLC
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

import logging

from c7n.actions import Action as BaseAction
from c7n_kube.provider import resources as kube_resources
from c7n.utils import local_session, chunks, type_schema
from c7n.exceptions import PolicyValidationError

from kubernetes.client import V1DeleteOptions

log = logging.getLogger('custodian.k8s.actions')


class Action(BaseAction):
    pass


class MethodAction(Action):
    method_spec = ()
    chunk_size = 20

    def validate(self):
        if not self.method_spec:
            raise NotImplementedError("subclass must define method_spec")
        return self

    def process(self, resources):
        m = self.manager.get_model()
        session = local_session(self.manager.session_factory)
        client = session.client(m.group, m.version)
        for resource_set in chunks(resources, self.chunk_size):
            self.process_resource_set(client, m, resource_set)

    def process_resource_set(self, client, model, resources):
        op_name = self.method_spec['op']
        for r in resources:
            log.info('%s %s' % (op_name, r))
        pass


class PatchAction(MethodAction):
    """
    Patches a resource

    Requires patch and namespaced attributes on the resource definition
    """
    def validate(self):
        if not self.manager.get_model().patch:
            raise PolicyValidationError('patch attribute not defined for resource')
        return self

    def get_permissions(self):
        patch = self.manager.get_model().patch
        return ''.join([a.capitalize() for a in patch.split('_')])

    def patch_resources(self, op, patch_args, namespaced, resources):
        for r in resources:
            patch_args['name'] = r['metadata']['name']
            if namespaced:
                patch_args['namespace'] = r['metadata']['namespace']
            op(**patch_args)


class DeleteAction(MethodAction):
    """
    Deletes a resource

    Requires delete and namespaced attributes on the resource definition
    """
    def validate(self):
        if not self.manager.get_model().delete:
            raise PolicyValidationError('delete attribute not defined for resource')
        return self

    def get_permissions(self):
        delete = self.manager.get_model().delete
        return ''.join([a.capitalize() for a in delete.split('_')])

    def delete_resources(self, op, delete_args, namespaced, resources):
        for r in resources:
            delete_args['name'] = r['metadata']['name']
            if namespaced:
                delete_args['namespace'] = r['metadata']['namespace']
            op(**delete_args)


class DeleteResource(DeleteAction):
    """
    Deletes a Resource

    .. code-block:: yaml
      policies:
        - name: delete-{resource}
          resource: k8s.{resource}
          filters:
            - 'metadata.name': 'test-{resource}'
          actions:
            - delete
    """
    schema = type_schema('delete')

    def process_resource_set(self, client, model, resources):
        body = V1DeleteOptions()
        op = getattr(client, model.delete)
        delete_args = {'body': body}
        self.delete_resources(op, delete_args, model.namespaced, resources)

    @classmethod
    def register_resources(klass, registry, resource_class):
        resource_type = resource_class.resource_type
        if hasattr(resource_type, 'delete') and hasattr(resource_type, 'namespaced'):
            resource_class.action_registry.register('delete', klass)


kube_resources.subscribe(kube_resources.EVENT_REGISTER, DeleteResource.register_resources)
