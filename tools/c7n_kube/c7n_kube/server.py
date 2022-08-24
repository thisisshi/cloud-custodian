import json
import os
import http.server

from c7n.config import Config
from c7n.handler import init_config
from c7n.policy import PolicyCollection
from c7n.resources import load_resources
from c7n.structure import StructureParser
from c7n.loader import DirectoryLoader

import logging

log = logging.getLogger("server")
logging.basicConfig()
log.setLevel(logging.INFO)


HOST = "127.0.0.1"

cert_location = os.environ.get("CERT_LOCATION", "cert.pem")
key_location = os.environ.get("KEY_LOCATION", "key.pem")

cert_location = "/etc/certs/cert.pem"
key_location = "/etc/certs/key.pem"


def dispatch_event(event):
    global policy_config, policy_data
    if policy_config is None:
        with open('config.json') as f:
            policy_data = json.load(f)
        policy_config = init_config(policy_data)
        load_resources(StructureParser().get_resource_types(policy_data))

    if not policy_data or not policy_data.get('policies'):
        return False

    policies = PolicyCollection.from_data(policy_data, policy_config)
    for p in policies:
        p.validate()
        p.push(event)

    return True


class AdmissionControllerServer(http.server.HTTPServer):
    """
    Admission Controller Server
    """

    def __init__(self, policy_dir, *args, **kwargs):
        self.policy_dir = policy_dir
        self.directory_loader = DirectoryLoader(Config.empty())
        policy_collection = self.directory_loader.load_directory(
            os.path.abspath(self.policy_dir))
        self.policy_collection = policy_collection.filter(
            providers=['k8s'], modes=['k8s-validating-controller'])
        super().__init__(*args, **kwargs)


class AdmissionControllerHandler(http.server.BaseHTTPRequestHandler):
    def get_request_body(self):
        token = self.rfile.read(int(self.headers["Content-length"]))
        res = token.decode("utf-8")
        return res

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        result = []
        for p in self.server.policy_collection.policies:
            result.append(p.data)
        self.wfile.write(json.dumps(result).encode('utf-8'))

    def do_POST(self):
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

        results = []
        failed_policies = []
        for p in self.server.policy_collection.policies:
            policy, allow = p.push(req)
            results.append(allow)
            if allow is False:
                failed_policies.append(
                    {
                        policy.name: policy.data.get('description')
                    }
                )

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(self.admission_response(
            req=req,
            allow=all(results),
            failed_policies=failed_policies).encode('utf-8'))

    def admission_response(self, req, allow=False, failed_policies=None):
        code = 200 if allow else 400
        message = 'OK'
        if failed_policies:
            message = f'Failed admission due to policies:{failed_policies}'

        return json.dumps({
            "apiVersion": "admission.k8s.io/v1",
            "kind": "AdmissionReview",
            "response": {
                "allowed": allow,
                "uid": req["request"]["uid"],
                "status": {
                    "code": code,
                    "message": message
                }
            }
        })


def init(port, policy_dir):
    server = AdmissionControllerServer(
        server_address=(HOST, port),
        RequestHandlerClass=AdmissionControllerHandler,
        policy_dir=policy_dir
    )
    log.info(f"Serving at {HOST} {port}")
    while True:
        server.serve_forever()
