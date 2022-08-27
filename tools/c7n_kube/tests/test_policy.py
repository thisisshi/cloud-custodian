# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from common_kube import KubeTest


class TestAdmissionControllerMode(KubeTest):
    def test_kube_admission_policy(self):
        factory = self.replay_flight_data()
        policy = self.load_policy(
            {
                'name': 'test-validator',
                'resource': 'k8s.pod',
                'mode': {
                    'type': 'k8s-validator',
                    'on-match': 'allow',
                    'operations': [
                        'CREATE',
                        'DELETE'
                    ]
                }
            }, session_factory=factory
        )
        expected = {
            'operations': ['CREATE', 'DELETE'],
            'resources': policy.resource_manager.get_model().plural.lower(),
            'group': policy.resource_manager.get_model().group.lower(),
            'apiVersions': policy.resource_manager.get_model().version.lower(),
            'scope': 'Namespaced' if policy.resource_manager.get_model().namespaced else 'Cluster'
        }
        match_values = policy.get_execution_mode().get_match_values()
        self.assertEqual(expected, match_values)
        event = self.get_event('create_pod')
        result, resources = policy.push(event)
        self.assertEqual(len(resources), 1)
        self.assertEqual(result, 'allow')

    def test_kube_event_filter(self):
        factory = self.replay_flight_data()
        policy = self.load_policy(
            {
                'name': 'test-event-filter',
                'resource': 'k8s.pod',
                'mode': {
                    'type': 'k8s-validator',
                    'on-match': 'deny',
                    'operations': [
                        'CREATE',
                    ]
                },
                'filters': [
                    {
                        'type': 'event',
                        'key': 'request.object.spec.containers[].image',
                        'value': 'nginx',
                        'op': 'eq',
                        'value_type': 'any_normalize'
                    }
                ]
            }, session_factory=factory
        )
        event = self.get_event('create_pod')
        result, resources = policy.push(event)
        self.assertEqual(len(resources), 1)
        self.assertEqual(result, 'deny')

    def test_kube_delete_event(self):
        factory = self.replay_flight_data()
        policy = self.load_policy(
            {
                'name': 'test-delete-pod',
                'resource': 'k8s.pod',
                'mode': {
                    'type': 'k8s-validator',
                    'on-match': 'deny',
                    'operations': [
                        'DELETE'
                    ]
                },
                'filters': [
                    # we should be able to filter on the attribbutes of the resource to be deleted
                    {'metadata.name': 'static-web'},
                ]
            }, session_factory=factory
        )
        event = self.get_event('delete_pod')
        result, resources = policy.push(event)
        self.assertTrue(resources)
        self.assertEqual(result, 'deny')

    def test_validator_warn_event(self):
        factory = self.replay_flight_data()
        policy = self.load_policy(
            {
                'name': 'test-warn-pod',
                'resource': 'k8s.pod',
                'mode': {
                    'type': 'k8s-validator',
                    'on-match': 'warn',
                    'operations': [
                        'CREATE'
                    ]
                }
            }, session_factory=factory
        )
        event = self.get_event('create_pod')
        result, resources = policy.push(event)
        self.assertTrue(resources)
        self.assertEqual(result, 'warn')

    def test_validator_warn_event_no_results(self):
        factory = self.replay_flight_data()
        policy = self.load_policy(
            {
                'name': 'test-warn-pod',
                'resource': 'k8s.pod',
                'mode': {
                    'type': 'k8s-validator',
                    'on-match': 'warn',
                    'operations': [
                        'CREATE'
                    ]
                },
                'filters': [
                    {'foo': 'bar'}
                ]
            }, session_factory=factory
        )
        event = self.get_event('create_pod')
        result, resources = policy.push(event)
        self.assertEqual(len(resources), 0)
        self.assertEqual(result, 'allow')

    def test_validator_allow_crd(self):
        factory = self.replay_flight_data()
        policy = self.load_policy(
            {
                'name': 'no-custom-resource-for-you',
                'resource': 'k8s.custom-namespaced-resource',
                'query': [
                    {
                        'plural': 'policyreports',
                        'group': 'wgpolicyk8s.io',
                        'version': 'v1alpha2'
                    }
                ],
                'mode': {
                    'type': 'k8s-validator',
                    'on-match': 'deny',
                    'operations': ['CREATE']
                }

            },
            session_factory=factory,
        )
        event = self.get_event('create_policyreport')
        result, resources = policy.push(event)
        self.assertEqual(result, 'deny')
        self.assertEqual(len(resources), 1)
