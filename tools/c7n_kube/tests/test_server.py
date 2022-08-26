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

    def test_server_handle_post(self):
        policies = {
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
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            with open(f"{temp_dir}/policy.yaml", "w+") as f:
                json.dump(policies, f)
            server_thread = threading.Thread(
                target=TestAdmissionControllerServer(
                    server_address=('0.0.0.0', 8088),
                    RequestHandlerClass=AdmissionControllerHandler,
                    policy_dir=temp_dir,
                    bind_and_activate=True,
                ).handle_request
            )
            server_thread.start()
            time.sleep(1)
            res = requests.get('http://0.0.0.0:8088')
            self.assertEqual(res.json(), policies['policies'])
            self.assertEqual(res.status_code, 200)
