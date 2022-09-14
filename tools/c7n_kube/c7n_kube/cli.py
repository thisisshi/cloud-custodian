# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import os
import argparse
import logging
import yaml

from c7n_kube.server import init

from c7n.config import Config
from c7n.loader import DirectoryLoader

log = logging.getLogger('custodian.k8s.cli')
logging.basicConfig(
    # TODO: make this configurable
    level=logging.INFO,
    format="%(asctime)s: %(name)s:%(levelname)s %(message)s")


PORT = '8800'
HOST = '0.0.0.0'

TEMPLATE = {
    "apiVersion": "admissionregistration.k8s.io/v1",
    "kind": "MutatingWebhookConfiguration",
    "metadata": {
        "name": "c7n-admission"
    },
    "webhooks": [
        {
            "name": "admission.cloudcustodian.io",
            "rules": [
                {
                    "operations": [],
                    "scope": "*",
                    "apiGroups": [],
                    "apiVersions": [],
                    "resources": [],
                }
            ],
            "admissionReviewVersions": [
                "v1",
                "v1beta1"
            ],
            "clientConfig": {
                "url": "${ENDPOINT}"
            },
            "sideEffects": "None",
            "failurePolicy": "Fail"
        }
    ]
}


def _parser():
    parser = argparse.ArgumentParser(description='Cloud Custodian Admission Controller')
    parser.add_argument('--port', type=int, help='Server port', nargs='?', default=PORT)
    parser.add_argument('--policy-dir', type=str, required=True, help='policy directory')
    parser.add_argument(
        '--on-exception', type=str.lower, required=False, default='warn',
        choices=['warn', 'deny'],
        help='warn or deny on policy exceptions')
    parser.add_argument(
        '--endpoint', default=None,
        help='Endpoint for webhook, used for generating manfiest')
    parser.add_argument(
        '--generate', default=False, action="store_true",
        help='Generate a k8s manifest for ValidatingWebhookConfiguration')
    return parser


def cli():
    """
    Cloud Custodian Admission Controller
    """
    parser = _parser()
    args = parser.parse_args()
    if args.generate:
        directory_loader = DirectoryLoader(Config.empty())
        policy_collection = directory_loader.load_directory(
            os.path.abspath(args.policy_dir))
        operations = []
        groups = []
        api_versions = []
        resources = []
        for p in policy_collection:
            mvals = p.get_execution_mode().get_match_values()
            operations.extend(mvals['operations'])
            groups.append(mvals['group'])
            api_versions.append(mvals['apiVersions'])
            resources.append(mvals['resources'])

        TEMPLATE['webhooks'][0]['rules'][0]['operations'] = sorted(list(set(operations)))
        TEMPLATE['webhooks'][0]['rules'][0]['apiGroups'] = sorted(list(set(groups)))
        TEMPLATE['webhooks'][0]['rules'][0]['apiVersions'] = sorted(list(set(api_versions)))
        TEMPLATE['webhooks'][0]['rules'][0]['resources'] = sorted(list(set(resources)))

        if args.endpoint:
            TEMPLATE['webhooks'][0]['clientConfig']['url'] = args.endpoint

        print(yaml.dump(TEMPLATE))
    else:
        init(args.port, args.policy_dir, args.on_exception)


if __name__ == '__main__':
    cli()
