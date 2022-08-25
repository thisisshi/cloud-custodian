import logging

from c7n.policy import PolicyExecutionMode, execution
from c7n.utils import type_schema, dumps


log = logging.getLogger('c7n_kube.policy')


class K8sEventMode(PolicyExecutionMode):
    pass


@execution.register('k8s-validating-controller')
class ValidatingControllerMode(K8sEventMode):
    """
    Validating Admission Controller Mode

    Actions are not compatible with Validating Admission Controller Mode

    Define matches, which are AND'd together across categories but are
    OR'd together within the same category, e.g.

    match:
        resources:
          - pods
        operations:
          - CREATE
          - UPDATE

    will match any event where the resources is pods and the operation is
    either CREATE or UPDATE

    Include a description to provide a message on failure:

    .. example::

      policies:
        - name: 'oui'
          resource: 'k8s.deployment'
          description: 'All deployments must only have label:foo'
          mode:
            type: k8s-validating-controller
            match:
              on-match: deny
              scope: Namespaced
              resources:
                - deployments
          filters:
            - type: value
              key: keys(metadata.labels)
              value: ['foo']
              op: ne
    """

    schema = type_schema(
        'k8s-validating-controller',
        required=['match'],
        **{
            'match': {
                'type': 'object',
                'properties': {
                    'on-match': {'enum': ['allow', 'deny']},
                    'scope': {'enum': ['Cluster', 'Namespaced']},
                    'group': {'type': 'array', 'items': {'type': 'string'}},
                    # this should probably just default to the c7n resource type?
                    'resources': {'type': 'array', 'items': {'type': 'string'}},
                    'apiVersions': {'type': 'array', 'items': {'type': 'string'}},
                    'operations': {
                        'type': 'array',
                        'items': {'enum': ['CREATE', 'UPDATE', 'DELETE', 'CONNECT']}}
                }
            }
        }
    )

    def _handle_scope(self, request, value):
        if value == '*':
            return True
        elif request.get('namespace') and value == 'Namespaced':
            return True
        elif request.get('namespace') and value == 'Cluster':
            return False
        return False

    def _handle_group(self, request, value):
        if '*' in value:
            return True
        group = request['resource']['group']
        if value == '' and group == 'core':
            return True
        return group in value

    def _handle_resources(self, request, value):
        if '*' in value or "*/*" in value:
            return True

        resource = request['resource']['resource']
        subresource = request.get('subResource')

        result = []

        for v in value:
            split = v.split('/')
            if len(split) == 2:
                # Matching all resources, but only specific subresources
                if split[0] == "*" and request['subresource'] == split[1]:
                    result.append(True)
                # Matching a specific resource and any subresource
                elif split[0] == resource and split[1] == '*':
                    result.append(True)
                # Matching a specific resource and subresource
                elif split[0] == resource and split[1] == subresource:
                    result.append(True)
                else:
                    result.append(False)
            elif len(split) == 1:
                result.append(resource == split[0])

        return any(result)

    def _handle_api_versions(self, request, value):
        if '*' in value:
            return True
        version = request['resource']['version']
        return version in value

    def _handle_operations(self, request, value):
        if '*' in value:
            return True
        return request['operation'] in value

    handlers = {
        'scope': _handle_scope,
        'group': _handle_scope,
        'resources': _handle_resources,
        'api_versions': _handle_api_versions,
        'operations': _handle_operations,
    }

    def _filter_event(self, request):
        model = self.policy.resource_manager.get_model()

        # set default values based on our models
        value = {
            'resources': self.policy.data.get('resources') or [model.name],
            'groups': self.policy.data.get('groups') or [model.group],
            'api_versions': self.policy.data.get('api_versions') or [model.version],
            'scope': self.policy.data.get('scope') or (
                'Namespaced' if model.namespaced else 'Cluster')
        }
        matched = []
        for k, v in value.items():
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
        action = self.policy.data['mode']['match'].get('on-match', 'deny')

        if not self.policy.is_runnable(event):
            return self.policy.name, True
        log.info(f"Got event:{event}")
        matched = self._filter_event(event['request'])
        if not matched:
            log.warning("Event not matched, skipping")
            return self.policy.name, True
        resources = [event['request']['object']]
        resources = self.policy.resource_manager.filter_resources(resources, event)
        resources = self.run_resource_set(event, resources)

        if action == 'allow' and resources:
            allow = True
        elif action == 'allow' and not resources:
            allow = False
        elif action == 'deny' and resources:
            allow = False
        elif action == 'deny' and not resources:
            allow = True

        return self.policy, allow
