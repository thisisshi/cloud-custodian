# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import base64
import json
import os
import http.server

from c7n.config import Config
from c7n.loader import DirectoryLoader

import logging

log = logging.getLogger("c7n_kube.server")
log.setLevel(logging.DEBUG)


HOST = "0.0.0.0"


class AdmissionControllerServer(http.server.HTTPServer):
    """
    Admission Controller Server
    """

    def __init__(self, policy_dir, on_exception='warn', *args, **kwargs):
        self.policy_dir = policy_dir
        self.on_exception = on_exception
        self.directory_loader = DirectoryLoader(Config.empty())
        policy_collection = self.directory_loader.load_directory(
            os.path.abspath(self.policy_dir))
        self.policy_collection = policy_collection.filter(modes=['k8s-validator'])
        log.info(f"Loaded {len(self.policy_collection)} policies")
        super().__init__(*args, **kwargs)


class AdmissionControllerHandler(http.server.BaseHTTPRequestHandler):
    def get_request_body(self):
        token = self.rfile.read(int(self.headers["Content-length"]))
        res = token.decode("utf-8")
        return res

    def do_GET(self):
        """
        Returns application/json list of your policies
        """
        self.send_response(200)
        self.end_headers()
        result = []
        for p in self.server.policy_collection.policies:
            result.append(p.data)
        self.wfile.write(json.dumps(result).encode('utf-8'))

    def do_POST(self):
        """
        Entrypoint for kubernetes webhook
        """
        req = self.get_request_body()
        log.info(req)
        try:
            req = json.loads(req)
        except Exception as e:
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return

        failed_policies = []
        warn_policies = []
        patches = []

        for p in self.server.policy_collection.policies:
            # fail_message and warning_message are set on exception
            warning_message = None
            deny_message = None
            try:
                result, resources = p.push(req)
            except Exception as e:
                # if a policy fails we simply warn
                result = self.server.on_exception
                if result == 'warn':
                    warning_message = f"Error in executing policy: {str(e)}"
                if result == 'deny':
                    deny_message = f"Error in executing policy: {str(e)}"
            if result == 'deny':
                failed_policies.append(
                    {
                        "name": p.name,
                        "description": deny_message or p.data.get('description', '')
                    }
                )
            if result == 'warn':
                warn_policies.append(
                    {
                        "name": p.name,
                        "description": warning_message or p.data.get('description', '')
                    }
                )

            if resources and result in ('allow', 'warn',):
                patches.extend(resources[0].get('c7n:patches', []))

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()

        if patches:
            patches = base64.b64encode(json.dumps(patches).encode('utf-8')).decode()

        response = self.admission_response(
            uid=req['request']['uid'],
            failed_policies=failed_policies,
            warn_policies=warn_policies,
            patches=patches
        )
        log.info(response)
        self.wfile.write(response.encode('utf-8'))

    def admission_response(self, uid, failed_policies=None, warn_policies=None, patches=None):
        code = 200 if len(failed_policies) == 0 else 400
        message = 'OK'
        warnings = []
        if failed_policies:
            message = f'Failed admission due to policies:{json.dumps(failed_policies)}'
        if warn_policies:
            for p in warn_policies:
                warnings.append(f"{p['name']}:{p['description']}")

        response = {
            "apiVersion": "admission.k8s.io/v1",
            "kind": "AdmissionReview",
            "response": {
                "allowed": False if failed_policies else True,
                "warnings": warnings,
                "uid": uid,
                "status": {
                    "code": code,
                    "message": message
                }
            }
        }

        if patches:
            patch = {
                "patchType": "JSONPatch",
                "patch": patches
            }
            response['response'].update(patch)

        return json.dumps(response)


def init(port, policy_dir, on_exception='warn', serve_forever=True):
    server = AdmissionControllerServer(
        server_address=(HOST, port),
        RequestHandlerClass=AdmissionControllerHandler,
        policy_dir=policy_dir,
        on_exception=on_exception,
    )
    log.info(f"Serving at {HOST} {port}")
    while True:
        server.serve_forever()
        # for testing purposes
        if not serve_forever:
            break
