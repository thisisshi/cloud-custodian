# Copyright 2016-2017 Capital One Services, LLC
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
"""
Cloud-Custodian Lambda Entry Point

Mostly this serves to load up the policy and dispatch
an event.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import logging
import json

from c7n.policy import PolicyCollection
from c7n.resources import load_resources
from c7n.utils import format_event
from c7n.config import Config


logging.root.setLevel(logging.DEBUG)
logging.getLogger('botocore').setLevel(logging.WARNING)
log = logging.getLogger('custodian.lambda')


def dispatch_event(event, context):

    error = event.get('detail', {}).get('errorCode')
    if error:
        log.debug("Skipping failed operation: %s" % error)
        return

    event['debug'] = True
    if event['debug']:
        log.info("Processing event\n %s", format_event(event))

    # policies file should always be valid in lambda so do loading naively
    with open('config.json') as f:
        policy_config = json.load(f)

    if not policy_config or not policy_config.get('policies'):
        return False

    # TODO. This enshrines an assumption of a single policy per lambda.
    options_overrides = policy_config[
        'policies'][0].get('mode', {}).get('execution-options', {})
    options = Config.empty(**options_overrides)

    load_resources()
    policies = PolicyCollection.from_data(policy_config, options)
    if policies:
        for p in policies:
            p.push(event, context)
    return True
