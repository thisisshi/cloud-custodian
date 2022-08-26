# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
import tempfile
import threading
import time

import requests

from c7n_kube.server import \
    AdmissionControllerServer, AdmissionControllerHandler

from common_kube import KubeTest


class TestAdmissionControllerServer(AdmissionControllerServer):
    def __init__(self, bind_and_activate=False, *args, **kwargs):
        super().__init__(
            bind_and_activate=bind_and_activate, *args, **kwargs)


class TestServer(KubeTest):

    def _server(self, port, policies):
        with tempfile.TemporaryDirectory() as temp_dir:
            with open(f"{temp_dir}/policy.yaml", "w+") as f:
                json.dump(policies, f)
            server_thread = threading.Thread(
                target=TestAdmissionControllerServer(
                    server_address=('0.0.0.0', port),
                    RequestHandlerClass=AdmissionControllerHandler,
                    policy_dir=temp_dir,
                    bind_and_activate=True,
                ).handle_request
            )
            server_thread.start()
            time.sleep(1)

    def test_server_load_non_k8s_policies(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with open(f"{temp_dir}/policy.yaml", "w+") as f:
                json.dump(
                    {"policies": [{'name': 'test', 'resource': 's3'}]}, f
                )
            with open(f"{temp_dir}/policy2.yaml", "w+") as f:
                json.dump(
                    {"policies": [{'name': 'test2', 'resource': 'ec2'}]}, f
                )
            with open(f"{temp_dir}/policy3.yaml", "w+") as f:
                json.dump(
                    {"policies": [{'name': 'test3', 'resource': 'ebs'}]}, f
                )
            server = TestAdmissionControllerServer(
                server_address=('0.0.0.0', 8080),
                RequestHandlerClass=AdmissionControllerHandler,
                policy_dir=temp_dir
            )

            self.assertEqual(len(server.policy_collection.policies), 0)

    def test_server_load_k8s_policies_no_mode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with open(f"{temp_dir}/policy.yaml", "w+") as f:
                json.dump(
                    {"policies": [{'name': 'test', 'resource': 'k8s.pod'}]}, f
                )
            with open(f"{temp_dir}/policy2.yaml", "w+") as f:
                json.dump(
                    {"policies": [{'name': 'test2', 'resource': 'k8s.deployment'}]}, f
                )
            with open(f"{temp_dir}/policy3.yaml", "w+") as f:
                json.dump(
                    {"policies": [{'name': 'test3', 'resource': 'k8s.service'}]}, f
                )
            server = TestAdmissionControllerServer(
                server_address=('0.0.0.0', 8082),
                RequestHandlerClass=AdmissionControllerHandler,
                policy_dir=temp_dir
            )

            self.assertEqual(len(server.policy_collection.policies), 0)

    def test_server_load_k8s_policies_proper_mode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with open(f"{temp_dir}/policy.yaml", "w+") as f:
                json.dump(
                    {
                        "policies": [
                            {
                                'name': 'test',
                                'resource': 'k8s.pod',
                                'mode': {
                                    'type': 'k8s-validator',
                                    'operations': ['CREATE']
                                }
                            }
                        ]
                    }, f
                )
            with open(f"{temp_dir}/policy2.yaml", "w+") as f:
                json.dump(
                    {
                        "policies": [
                            {
                                'name': 'test2',
                                'resource': 'k8s.deployment',
                                'mode': {
                                    'type': 'k8s-validator',
                                    'operations': ['CREATE']
                                }
                            }
                        ]
                    }, f
                )
            with open(f"{temp_dir}/policy3.yaml", "w+") as f:
                json.dump(
                    {"policies": [{'name': 'test3', 'resource': 'k8s.service'}]}, f
                )
            server = TestAdmissionControllerServer(
                server_address=('0.0.0.0', 8080),
                RequestHandlerClass=AdmissionControllerHandler,
                policy_dir=temp_dir
            )

            # we should only have 2 policies here since there's only 2 policies with the right mode
            self.assertEqual(len(server.policy_collection.policies), 2)

    def test_server_handle_get_empty_policies(self):
        policies = {
            'policies': []
        }
        self._server(8088, policies)
        res = requests.get('http://0.0.0.0:8088')
        self.assertEqual(res.json(), [])
        self.assertEqual(res.status_code, 200)

    def test_server_handle_post_no_policies(self):
        policies = {
            'policies': []
        }
        port = 8088
        self._server(port, policies)
        event = self.get_event('create_pod')
        res = requests.post(f'http://0.0.0.0:{port}', json=event)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            {
                'apiVersion': 'admission.k8s.io/v1',
                'kind': 'AdmissionReview',
                'response': {
                    'allowed': True,
                    'uid': '662c3df2-ade6-4165-b395-770857bc17b7',
                    'status': {
                        'code': 200,
                        'message': 'OK'
                    }
                }
            },
            res.json()
        )

    def test_server_handle_post_policies_deny_on_match(self):
        policies = {
            'policies': [
                {
                    'name': 'test-validator',
                    'resource': 'k8s.pod',
                    'mode': {
                        'type': 'k8s-validator',
                        'on-match': 'deny',
                        'operations': [
                            'CREATE',
                        ]
                    }
                }
            ]
        }
        port = 8088
        self._server(port, policies)
        event = self.get_event('create_pod')
        res = requests.post(f'http://0.0.0.0:{port}', json=event)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()['response']['allowed'])

    def test_server_handle_post_policies_allow_on_match(self):
        policies = {
            'policies': [
                {
                    'name': 'test-validator',
                    'resource': 'k8s.pod',
                    'mode': {
                        'type': 'k8s-validator',
                        'on-match': 'allow',
                        'operations': [
                            'CREATE',
                        ]
                    }
                }
            ]
        }
        port = 8088
        self._server(port, policies)
        event = self.get_event('create_pod')
        res = requests.post(f'http://0.0.0.0:{port}', json=event)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['response']['allowed'])

    def test_server_handle_post_policies_deny_on_match_multiple(self):
        policies = {
            'policies': [
                {
                    'name': 'test-validator-deployment',
                    'resource': 'k8s.deployment',
                    'description': 'description deployment',
                    'mode': {
                        'type': 'k8s-validator',
                        'on-match': 'deny',
                        'operations': [
                            'CREATE',
                        ]
                    }
                },
                {
                    'name': 'test-validator',
                    'resource': 'k8s.pod',
                    'description': 'description 1',
                    'mode': {
                        'type': 'k8s-validator',
                        'on-match': 'deny',
                        'operations': [
                            'CREATE',
                        ]
                    }
                },
                {
                    'name': 'test-validator-2',
                    'description': 'description 2',
                    'resource': 'k8s.pod',
                    'mode': {
                        'type': 'k8s-validator',
                        'on-match': 'deny',
                        'operations': [
                            'CREATE',
                        ]
                    }
                }
            ]
        }
        port = 8088
        self._server(port, policies)
        event = self.get_event('create_pod')
        res = requests.post(f'http://0.0.0.0:{port}', json=event)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()['response']['allowed'])
        failures = json.loads(
            res.json()['response']['status']['message'].split(':', 1)[-1]
        )
        self.assertEqual(len(failures), 2)
        self.assertEqual(failures[0], {'test-validator': 'description 1'})
        self.assertEqual(failures[1], {'test-validator-2': 'description 2'})
