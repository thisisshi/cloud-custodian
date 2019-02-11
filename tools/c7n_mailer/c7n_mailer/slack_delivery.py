# Copyright 2018 Capital One Services, LLC
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
import logging
import time

import requests
import six
from c7n_mailer.utils import get_rendered_jinja
from c7n_mailer.utils_email import is_email


class SlackDelivery(object):

    def __init__(self, slack_token, slack_webhook, cache_engine, email_handler):
        # TODO: get rid of email_handler dep
        self.log = logging.getLogger(__name__)
        self.caching = cache_engine
        self.templates_folders = email_handler.templates_folders
        self.slack_token = slack_token
        self.slack_webhook = slack_webhook
        self.email_handler = email_handler

    def get_to_addrs_slack_messages_map(self, sqs_message):
        """
        Returns a mapping of slack identities to a list of rendered
        request bodies for use when delivering slack notifications.

        i.e. {'slackuser': ['requestbody']}

        Supports the following formats:
        - slack://owners
            `owners` are specified by the mailer configuration file when
            initialized and are looked up via the resource's tag value.

        - slack://tag/{user-specified-tag}
            Users can specify a tag to query from, e.g.:
                slack://tag/notify-channel
                slack://tag/slack-email
            if the tag value is an email address, this function will do
            a lookup against Slack's users to find the id and return
            a template with the proper user id. Otherwise, it will assume
            the value is a channel name

        - slack://{email@address.com}
            Users can specify an email address to receive slack notifications.
            this function will performm a lookup against Slack's users to
            find  the user's id and return the rendered template.

        - slack://#{channel}
            Users can specify a channel to send notifications. This requires
            the use of a Slack token in the configuration file.

        - slack://webhook/#{channel}
            Users can specify a channel to send notifications. This requires
            the use of a Slack Webhook in the configuration file.

        - https://hooks.slack.com/...
            Users can specify a direct webhook from which to receive Slack
            notifications from.
        """
        resource_list = []
        resource_list.extend(sqs_message['resources'])

        slack_messages = {}

        for target in sqs_message.get('action', ()).get('to'):
            if target == 'slack://owners':
                to_addrs_to_resources_map = \
                    self.email_handler.get_email_to_addrs_to_resources_map(sqs_message)
                for to_addrs, resources in six.iteritems(to_addrs_to_resources_map):
                    resolved_addrs = self.retrieve_user_im(list(to_addrs))

                    if not resolved_addrs:
                        continue

                    for address, slack_target in resolved_addrs.items():
                        slack_messages.setdefault(address, []).append(
                            get_rendered_jinja(slack_target, sqs_message, resources,
                            'slack_template', 'slack_default', self.templates_folders))

                continue
            elif target.startswith('slack://tag/'):
                for r in resource_list:
                    if 'Tags' not in r:
                        continue

                    tag_name = target.split('tag/', 1)[1]
                    tag_map = {t['Key']: t['Value'] for t in r.get('Tags', {})}
                    tag = tag_map.get(tag_name, None)

                    if not tag:
                        continue

                    if is_email(tag):
                        address = list(self.retrieve_user_im([tag]).keys())[0]
                        slack_target = list(self.retrieve_user_im([tag]).values())[0]
                    else:  # assume tag is a channel name
                        address = tag
                        slack_target = tag

                    slack_messages.setdefault(address, []).append(
                        get_rendered_jinja(slack_target, sqs_message, [r],
                        'slack_template', 'slack_default', self.templates_folders))
                continue
            elif target.startswith('https://hooks.slack.com/'):
                address = target
                slack_target = target
            elif target.startswith('slack://webhook/#') and self.slack_webhook:
                address = self.slack_webhook
                slack_target = target.split('slack://webhook/#', 1)[1]
            elif target.startswith('slack://') and is_email(target.split('slack://', 1)[1]):
                resolved_addrs = self.retrieve_user_im([target.split('slack://', 1)[1]])
                address = list(resolved_addrs.keys())[0]
                slack_target = list(resolved_addrs.values())[0]
            elif target.startswith('slack://#'):
                address = target.split('slack://#', 1)[1]
                slack_target = address
            else:
                continue
            slack_messages.setdefault(address, []).append(
                get_rendered_jinja(slack_target, sqs_message, resource_list,
                'slack_template', 'slack_default', self.templates_folders))
        return slack_messages

    def slack_handler(self, slack_messages):
        """
        Entry point for delivering Slack Messages
        """
        for key, payload in slack_messages.items():
            for p in payload:
                self.send_slack_msg(key, p)
        return True

    def retrieve_user_im(self, email_addresses):
        """
        Retrieves Slack user ID from email address

        This requires the following permissions in Slack:

        users:read
        users:read_email
        """
        email_to_id_map = {}
        if not self.slack_token:
            self.log.info("No Slack token found.")
        for address in email_addresses:
            if self.caching and self.caching.get(address):
                self.log.debug('Got Slack metadata from cache for: %s' % address)
                email_to_id_map[address] = self.caching.get(address)
                continue
            response = requests.post(
                url='https://slack.com/api/users.lookupByEmail',
                data={'email': address},
                headers={'Content-Type': 'application/x-www-form-urlencoded',
                         'Authorization': 'Bearer %s' % self.slack_token}).json()
            if not response["ok"]:
                if "headers" in response.keys() and "Retry-After" in response["headers"]:
                    self.log.info(
                        "Slack API rate limiting. Waiting %d seconds",
                        int(response.headers['retry-after']))
                    time.sleep(int(response.headers['Retry-After']))
                    continue
                elif response["error"] == "invalid_auth":
                    self.log.error('Invalid Slack token')
                elif response["error"] == "users_not_found":
                    self.log.info("Slack user ID not found: %s" % address)
                    if self.caching:
                        self.caching.set(address, {})
                    continue
                else:
                    self.log.warning("Slack Response: {}".format(response))
            else:
                slack_user_id = response['user']['id']
                if 'enterprise_user' in response['user'].keys():
                    slack_user_id = response['user']['enterprise_user']['id']
                self.log.debug(
                    "Slack account %s found for user %s", slack_user_id, address)
                if self.caching:
                    self.log.debug('Writing user: %s metadata to cache.', address)
                    self.caching.set(address, slack_user_id)
                email_to_id_map[address] = slack_user_id
        return email_to_id_map

    def send_slack_msg(self, key, message_payload):
        """
        Send Slack Messages

        If key is a Slack webhook, send directly to the webhook
        Othwerwise, we use the API (/api/chat.postMessage)

        This requires the following permissions in Slack:
        im:write
        chat:write:bot
        """
        if key.startswith('https://hooks.slack.com/'):
            response = requests.post(
                url=key,
                data=message_payload,
                headers={'Content-Type': 'application/json'})
        else:
            response = requests.post(
                url='https://slack.com/api/chat.postMessage',
                data=message_payload,
                headers={'Content-Type': 'application/json;charset=utf-8',
                         'Authorization': 'Bearer %s' % self.slack_token})

        if response.status_code == 429 and "Retry-After" in response.headers:
            self.log.info("Slack API rate limiting. Waiting %d seconds",
                int(response.headers['retry-after']))
            time.sleep(int(response.headers['Retry-After']))
            return
        elif response.status_code != 200:
            self.log.info("Error in sending Slack message: %s" % response.json())
            return

        return response
