# Copyright The Cloud Custodian Authors.
# SPD-License-Identifier: Apache-2.0
import copy
import logging

import jmespath
import jq
import jsonpatch
import re

from c7n.actions import Action as BaseAction
from c7n.utils import local_session, chunks, type_schema
from c7n.exceptions import PolicyValidationError

from kubernetes.client import V1DeleteOptions

log = logging.getLogger('custodian.k8s.actions')


class Action(BaseAction):
    pass


class EventAction(BaseAction):
    pass


class MethodAction(Action):
    method_spec = ()
    chunk_size = 20

    def validate(self):
        if not self.method_spec:
            raise NotImplementedError("subclass must define method_spec")
        return self

    def process(self, resources):
        session = local_session(self.manager.session_factory)
        m = self.manager.get_model()
        client = session.client(m.group, m.version)
        for resource_set in chunks(resources, self.chunk_size):
            self.process_resource_set(client, resource_set)

    def process_resource_set(self, client, resources):
        op_name = self.method_spec['op']
        op = getattr(client, op_name)
        for r in resources:
            op(name=r['metadata']['name'])


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

    def patch_resources(self, client, resources, **patch_args):
        op = getattr(client, self.manager.get_model().patch)
        namespaced = self.manager.get_model().namespaced
        for r in resources:
            patch_args['name'] = r['metadata']['name']
            if namespaced:
                patch_args['namespace'] = r['metadata']['namespace']
            op(**patch_args)


class PatchResource(PatchAction):
    """
    Patches a resource

    .. code-block:: yaml

      policies:
        - name: scale-resource
          resource: k8s.deployment # k8s.{resource}
          filters:
            - 'metadata.name': 'test-{resource}'
          actions:
            - type: patch
              options:
                spec:
                  replicas: 0
    """
    schema = type_schema(
        'patch',
        **{'options': {'type': 'object'}}
    )

    def process_resource_set(self, client, resources):
        patch_args = {'body': self.data.get('options', {})}
        self.patch_resources(client, resources, **patch_args)

    @classmethod
    def register_resources(klass, registry, resource_class):
        model = resource_class.resource_type
        if hasattr(model, 'patch') and hasattr(model, 'namespaced'):
            resource_class.action_registry.register('patch', klass)


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

    def delete_resources(self, client, resources, **delete_args):
        op = getattr(client, self.manager.get_model().delete)
        namespaced = self.manager.get_model().namespaced
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
        - name: delete-resource
          resource: k8s.pod # k8s.{resource}
          filters:
            - 'metadata.name': 'test-{resource}'
          actions:
            - delete
    """
    schema = type_schema(
        'delete',
        grace_period_seconds={'type': 'integer'},
    )

    def process_resource_set(self, client, resources):
        grace = self.data.get('grace_period_seconds', 30)
        body = V1DeleteOptions()
        body.grace_period_seconds = grace
        delete_args = {'body': body}
        self.delete_resources(client, resources, **delete_args)

    @classmethod
    def register_resources(klass, registry, resource_class):
        model = resource_class.resource_type
        if ('delete' not in resource_class.action_registry and
            hasattr(model, 'delete') and
                hasattr(model, 'namespaced')):
            resource_class.action_registry.register('delete', klass)


class EventPatchAction(EventAction):
    """
    Given a jq expression set the value

    .. code-block:: yaml

      policies:
        - name: foo
          actions:
            - type: event-patch
              key: spec.containers[0].name
              value: 'prefix-{value}'
    """

    schema = type_schema(
        'event-patch',
        key={'type': 'string'},
        value={'type': 'string'},
        required=['key', 'value']
    )

    def get_value(self, resource, event):

        def extract_value(original, regex, resource):
            for i in regex.finditer(original):
                element = i.group()
                search_path = element.split(':', 1)[-1]
                search_path = search_path.rsplit('}', 1)[0]
                found = jmespath.search(search_path, resource)
                original = original.replace(element, found)
            return original

        original = self.data['value']
        event_compiled = re.compile(r'{event:[\w.\[\]\d]*}')
        resource_compiled = re.compile(r'{resource:[\w.\[\]\d]*}')
        if resource_compiled.findall(original):
            original = extract_value(original, resource_compiled, resource)
        if event_compiled.findall(original):
            original = extract_value(original, event_compiled, event)
        return original

    def process_resource(self, resource, event):

        src = copy.deepcopy(resource)
        dst = copy.deepcopy(src)

        value = self.get_value(resource, event)

        compiled = jq.compile(f'.{self.data["key"]}|={value}')
        dst = compiled.input(dst).first()
        patch = jsonpatch.make_patch(src, dst)

        resource.setdefault('c7n:patches', [])
        resource['c7n:patches'].extend(patch.patch)

    def process(self, resources, event):
        for r in resources:
            self.process_resource(r, event)

    @classmethod
    def register_resources(klass, registry, resource_class):
        resource_class.action_registry.register('event-patch', klass)
