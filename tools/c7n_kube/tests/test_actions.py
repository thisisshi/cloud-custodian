# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from common_kube import KubeTest
from test_policy import TestAdmissionControllerMode

from c7n.exceptions import PolicyValidationError


class TestDeleteAction(KubeTest):
    def test_delete_action(self):
        factory = self.replay_flight_data()
        p = self.load_policy(
            {
                'name': 'delete-namespace',
                'resource': 'k8s.namespace',
                'filters': [
                    {'metadata.name': 'test'}
                ],
                'actions': [
                    {'type': 'delete'}
                ]
            },
            session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client('Core', 'V1')
        namespaces = client.list_namespace().to_dict()['items']
        test_namespace = [n for n in namespaces if n['metadata']['name'] == 'test'][0]
        self.assertEqual(test_namespace['status']['phase'], 'Terminating')

    def test_delete_namespaced_resource(self):
        factory = self.replay_flight_data()
        p = self.load_policy(
            {
                'name': 'delete-service',
                'resource': 'k8s.service',
                'filters': [
                    {'metadata.name': 'hello-node'}
                ],
                'actions': [
                    {'type': 'delete'}
                ]
            },
            session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client('Core', 'V1')
        namespaces = client.list_service_for_all_namespaces().to_dict()['items']
        hello_node_service = [n for n in namespaces if n['metadata']['name'] == 'hello-node']
        self.assertFalse(hello_node_service)


class TestPatchAction(KubeTest):
    def test_patch_action(self):
        factory = self.replay_flight_data()
        p = self.load_policy(
            {
                'name': 'test-patch',
                'resource': 'k8s.deployment',
                'filters': [
                    {'metadata.name': 'hello-node'},
                    {'spec.replicas': 1}
                ],
                'actions': [
                    {
                        'type': 'patch',
                        'options': {
                            'spec': {
                                'replicas': 2
                            }
                        }
                    }
                ]
            },
            session_factory=factory
        )
        resources = p.run()
        self.assertTrue(len(resources), 1)
        client = factory().client('Apps', 'V1')
        deployments = client.list_deployment_for_all_namespaces().to_dict()['items']
        hello_node_deployment = [d for d in deployments if d['metadata']['name'] == 'hello-node'][0]
        self.assertEqual(hello_node_deployment['spec']['replicas'], 2)


class TestEventAction(TestAdmissionControllerMode):

    def test_validator_event_label(self):
        factory = self.replay_flight_data()
        policy = self.load_policy(
            {
                'name': 'label-pod',
                'resource': 'k8s.pod',
                'mode': {
                    'type': 'k8s-validator',
                    'on-match': 'allow',
                    'operations': ['CREATE']
                },
                'actions': [
                    {
                        'type': 'event-label',
                        'labels': {
                            'foo': 'bar',
                            'role': 'different role',
                            'test': None
                        }
                    }
                ]

            },
            session_factory=factory,
        )
        event = self.get_event('create_pod')
        result, resources = policy.push(event)
        self.assertEqual(result, 'allow')
        self.assertEqual(len(resources), 1)
        self.assertEqual(len(resources[0]['c7n:patches']), 3)
        self.assertEqual(
            resources[0]['c7n:patches'],
            [
                {'op': 'remove', 'path': '/metadata/labels/test'},
                {"op": "add", "path": "/metadata/labels/foo", "value": "bar"},
                {"op": "replace", "path": "/metadata/labels/role", "value": "different role"},
            ]
        )

    def test_validator_event_auto_label_user(self):
        factory = self.replay_flight_data()
        policy = self.load_policy(
            {
                'name': 'label-pod',
                'resource': 'k8s.pod',
                'mode': {
                    'type': 'k8s-validator',
                    'on-match': 'allow',
                    'operations': ['CREATE']
                },
                'actions': [
                    {
                        'type': 'auto-label-user',
                    }
                ]

            },
            session_factory=factory,
        )
        event = self.get_event('create_pod')
        result, resources = policy.push(event)
        self.assertEqual(result, 'allow')
        self.assertEqual(len(resources), 1)
        self.assertEqual(len(resources[0]['c7n:patches']), 1)
        self.assertEqual(
            resources[0]['c7n:patches'],
            [{"op": "add", "path": "/metadata/labels/OwnerContact", "value": "kubernetes-admin"}]
        )

    def test_validator_action_validate(self):
        factory = self.replay_flight_data()
        with self.assertRaises(PolicyValidationError):
            self.load_policy(
                {
                    'name': 'label-pod',
                    'resource': 'k8s.pod',
                    'mode': {
                        'type': 'k8s-validator',
                        'on-match': 'allow',
                        'operations': ['CREATE']
                    },
                    'actions': [
                        {
                            'type': 'label',
                            'labels': {
                                'foo': 'bar'
                            }
                        }
                    ]

                },
                session_factory=factory,
            )

    def test_validator_action_event_patch(self):
        factory = self.replay_flight_data()
        policy = self.load_policy(
            {
                'name': 'change-image',
                'resource': 'k8s.pod',
                'mode': {
                    'type': 'k8s-validator',
                    'on-match': 'allow',
                    'operations': ['CREATE']
                },
                'actions': [
                    {
                        'type': 'event-patch',
                        'key': 'spec.containers[].image',
                        'value': '"prefix-{resource:kind}-"+.+"-{event:kind}"'
                    }
                ]

            },
            session_factory=factory,
        )
        event = self.get_event('create_pod')
        result, resources = policy.push(event)
        self.assertEqual(
            resources[0]['c7n:patches'],
            [
                {
                    'op': 'replace',
                    'path': '/spec/containers/0/image',
                    'value': 'prefix-Pod-ubuntu-AdmissionReview'},
                {
                    'op': 'replace',
                    'path': '/spec/containers/1/image',
                    'value': 'prefix-Pod-nginx-AdmissionReview'
                }
            ]
        )

    def test_validator_action_event_patch_delete(self):
        factory = self.replay_flight_data()
        policy = self.load_policy(
            {
                'name': 'change-image',
                'resource': 'k8s.pod',
                'mode': {
                    'type': 'k8s-validator',
                    'on-match': 'allow',
                    'operations': ['CREATE']
                },
                'actions': [
                    {
                        'type': 'event-patch',
                        'key': 'spec.containers[].image',
                        'delete': True
                    }
                ]

            },
            session_factory=factory,
        )
        event = self.get_event('create_pod')
        result, resources = policy.push(event)
        breakpoint()
        self.assertEqual(
            resources[0]['c7n:patches'],
            [
                {
                    'op': 'remove',
                    'path': '/spec/containers/0/image',
                {
                    'op': 'remove',
                    'path': '/spec/containers/1/image',
                }
            ]
        )
