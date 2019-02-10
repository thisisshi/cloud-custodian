# Copyright 2017 Capital One Services, LLC
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
SQS Message Processing
===============

"""
import base64
import json
import logging
import six
import traceback
import zlib

from contextlib import ContextDecorator

from .ldap_lookup import LdapLookup, Redis, LocalSqlite
from .email_delivery import EmailDelivery
from .sns_delivery import SnsDelivery

from c7n_mailer.utils import kms_decrypt

DATA_MESSAGE = "maidmsg/1.0"


class ParallelSQSProcessor(ContextDecorator):
    def __init__(self, parallel, sqs_messages):
        self.log = logging.getLogger(__name__)
        self.sqs_messages = sqs_messages
        self.parallel = parallel

    def __call__(self, f):
        def call(*args, **kwargs):
            sqs_message = kwargs['sqs_message']
            self.log.debug("Message id: %s received %s" % (sqs_message['MessageId'],
                    sqs_message.get('MessageAttributes', '')))
            msg_kind = sqs_message.get('MessageAttributes', {}).get('mtype', {})
            if not msg_kind.get('StringValue') == DATA_MESSAGE:
                warning_msg = 'Unknown sqs_message or sns format %s' % (
                    sqs_message['Body'][:50])
                self.log.warning(warning_msg)
            else:
                self.process_sqs_message(encoded_sqs_message=sqs_message)
            self.log.debug('Processed sqs_message')

            if self.parallel:
                self.process_pool.apply_async(f, **kwargs)
            else:
                f(**kwargs)

            self.log.debug('Processed sqs_message')
            self.sqs_messages.ack(sqs_message)

        return call

    def __enter__(self):
        # lambda doesn't support multiprocessing, so we don't instantiate any mp stuff
        # unless it's being run from CLI on a normal system with SHM
        if self.parallel:
            import multiprocessing
            self.process_pool = multiprocessing.Pool(processes=self.max_num_processes)
        return self

    def __exit__(self, *exc):
        self.log.info('No sqs_messages left on the queue, exiting c7n_mailer.')

        if self.parallel:
            self.process_pool.close()
            self.process_pool.join()


class MailerSqsQueueIterator(object):
    # Copied from custodian to avoid runtime library dependency
    msg_attributes = ['sequence_id', 'op', 'ser']

    def __init__(self, aws_sqs, queue_url, limit=0, timeout=10):
        self.log = logging.getLogger('__name__')
        self.aws_sqs = aws_sqs
        self.queue_url = queue_url
        self.limit = limit
        self.timeout = timeout
        self.messages = []

    def __iter__(self):
        return self

    def __next__(self):
        if self.messages:
            return self.messages.pop(0)
        response = self.aws_sqs.receive_message(
            QueueUrl=self.queue_url,
            WaitTimeSeconds=self.timeout,
            MaxNumberOfMessages=3,
            MessageAttributeNames=self.msg_attributes)

        msgs = response.get('Messages', [])
        self.log.debug('Messages received %d', len(msgs))
        for m in msgs:
            self.messages.append(m)
        if self.messages:
            return self.messages.pop(0)
        raise StopIteration()

    next = __next__  # python2.7

    def ack(self, m):
        self.aws_sqs.delete_message(
            QueueUrl=self.queue_url,
            ReceiptHandle=m['ReceiptHandle'])


class MailerSqsQueueProcessor(object):

    def __init__(self, config, session, max_num_processes=16):
        self.log = logging.getLogger(__name__)
        self.sqs = self.session.client('sqs')
        self.config = config
        self.session = session
        self.max_num_processes = max_num_processes
        self.receive_queue = self.config['queue_url']
        if self.config.get('debug', False):
            self.log.debug('debug logging is turned on from mailer config file.')
            self.log.setLevel(logging.DEBUG)

        # set up cache engine, ldap lookup etc.
        if self.config.get('cache_engine') == 'redis':
            redis_host = self.config.get('redis_host')
            redis_port = self.config.get('redis_port')
            self.cache_engine = Redis(redis_host=redis_host, redis_port=redis_port, db=-1)
        elif self.config.get('cache_engine') == 'sqlite':
            try:
                import sqlite3 # noqa
            except ImportError:
                raise RuntimeError('No sqlite available: stackoverflow.com/q/44058239')
            self.cache_engine = LocalSqlite(
                self.config.get('ldap_cache_file', '/var/tmp/ldap.cache'))
        else:
            self.cache_engine = None

        if self.config.get('ldap_uri'):
            ldap_uri = self.config.get('ldap_uri')
            ldap_bind_user = self.config.get('ldap_bind_user', None)
            ldap_bind_password = kms_decrypt(self.config, self.session, 'ldap_bind_password')
            ldap_bind_dn = self.config.get('ldap_bind_dn')
            ldap_email_key = self.config.get('ldap_email_key', 'mail')
            ldap_manager_attr = self.config.get('ldap_manager_attr', 'manager')
            ldap_uid_attr = self.config.get('ldap_uid_attribute', 'sAMAccountName')
            ldap_uid_regex = self.config.get('ldap_uid_regex', None)

            self.ldap_lookup = LdapLookup(ldap_uri, ldap_bind_user, ldap_bind_password,
                ldap_bind_dn, ldap_email_key, ldap_manager_attr, ldap_uid_attr,
                ldap_uid_regex, self.cache_engine)
        else:
            self.ldap_lookup = None

        self.email_delivery = EmailDelivery(
            session=self.session,
            ldap_lookup=self.ldap_lookup,
            org_domain=self.config.get('org_domain'),
            contact_tags=self.config.get('contact_tags'),
            account_emails=self.config.get('account_emails'),
            templates_folders=self.config.get('templates_folders'),
            from_address=self.config.get('from_address'),
            ldap_uid_tag_keys=self.config.get('ldap_uid_tags'),
            smtp_server=self.config.get('smtp_server'),
            smtp_port=self.config.get('smtp_port', 25),
            smtp_ssl=self.config.get('smtp_ssl', True),
            smtp_username=self.config.get('smtp_username'),
            smtp_password=self.config.get('smtp_password'),
            ses_region=self.config.get('ssl_region')
        )

        self.sns_delivery = SnsDelivery(
            cross_accounts=self.config.get('cross_accounts', []),
            contact_tags=self.config.get('contact_tags', []),
            templates_folders=self.config.get('templates_folders'),
            session=self.session,
        )

    def unpack_sqs_message(self, encoded_sqs_message):
        body = encoded_sqs_message['Body']
        try:
            body = json.dumps(json.loads(body)['Message'])
        except ValueError:
            pass
        sqs_message = json.loads(zlib.decompress(base64.b64decode(body)))

        self.log.debug("Got account:%s message:%s %s:%d policy:%s recipients:%s" % (
            sqs_message.get('account', 'na'),
            encoded_sqs_message['MessageId'],
            sqs_message['policy']['resource'],
            len(sqs_message['resources']),
            sqs_message['policy']['name'],
            ', '.join(sqs_message['action'].get('to'))))
        return sqs_message

    def process_sqs_message(self, encoded_sqs_message):
        """
        Process SQS message and delivery to their respective destinations

        Supports:
        - Email via AWS SES
        - Email via SMTP
        - AWS SNS
        - Slack
        - Datadog

        This function when processing sqs messages will only deliver messages over email or sns
        If you explicitly declare which tags are aws_usernames (synonymous with ldap uids)
        in the ldap_uid_tags section of your mailer.yml, we'll do a lookup of those emails
        (and their manager if that option is on) and also send emails there.
        """
        sqs_message = self.unpack_sqs_message(encoded_sqs_message)

        # get the map of email_to_addresses to mimetext messages (with resources baked in)
        # and send any emails (to SES or SMTP) if there are email addresses found
        to_addrs_to_email_messages_map = self.email_delivery.get_to_addrs_email_messages_map(sqs_message) # noqa
        for email_to_addrs, mimetext_msg in six.iteritems(to_addrs_to_email_messages_map):
            self.email_delivery.send_c7n_email(sqs_message, list(email_to_addrs), mimetext_msg)

        # this sections gets the map of sns_to_addresses to rendered_jinja messages
        # (with resources baked in) and delivers the message to each sns topic
        sns_message_packages = self.sns_delivery.get_sns_message_packages(sqs_message)
        self.sns_delivery.deliver_sns_messages(sns_message_packages, sqs_message)

        self.handle_slack_notifications(sqs_message)
        self.handle_datadog_notifications(sqs_message)

    def handle_slack_notifications(self, sqs_message):
        """
        Optionally handle slack notifications
        """
        if any(e.startswith('slack') or e.startswith('https://hooks.slack.com/')
                for e in sqs_message.get('action', ()).get('to')):
            from .slack_delivery import SlackDelivery
            if self.config.get('slack_token'):
                slack_token = kms_decrypt(self.config, self.session, 'slack_token')
            slack_delivery = SlackDelivery(
                slack_token=slack_token,
                slack_webhook=self.config.get('slack_webhook'),
                templates_folders=self.config.get('templates_folders'),
                email_handler=self.email_delivery,
                cache_engine=self.cache_engine
            )
            slack_messages = slack_delivery.get_to_addrs_slack_messages_map(sqs_message)
            try:
                slack_delivery.slack_handler(sqs_message, slack_messages)
            except Exception:
                traceback.print_exc()
                pass

    def handle_datadog_notifications(self, sqs_message):
        """
        Optionally handle datadog notifications
        """
        if any(e.startswith('datadog') for e in sqs_message.get('action', ()).get('to')):
            from .datadog_delivery import DataDogDelivery
            datadog_delivery = DataDogDelivery(
                datadog_api_key=self.config.get('datadog_api_key'),
                datadog_app_key=self.config.get('datadog_application_key')
            )
            datadog_message_packages = datadog_delivery.get_datadog_message_packages(sqs_message) # noqa
            try:
                datadog_delivery.deliver_datadog_messages(datadog_message_packages, sqs_message)
            except Exception:
                traceback.print_exc()
                pass

    def run(self, parallel=False):
        """
        Entry point for SQS Queue processing of c7n mail

        Cases:
        - resource is tagged CreatorName: 'milton', ldap_tag_uids has CreatorName,
            we do an ldap lookup, get milton's email and send him an email
        - you put an email in the to: field of the notify of your policy, we send an email
            for all resources enforced by that policy
        - you put an sns topic in the to: field of the notify of your policy, we send an sns
            message for all resources enforce by that policy
        - an lambda enforces a policy based on an event, we lookup the event aws username, get their
            ldap email and send them an email about a policy enforcement (from lambda) for the event
        - resource-owners has a list of tags, SupportEmail, OwnerEmail, if your resources
            include those tags with valid emails, we'll send an email for those resources
            any others
        - resource-owners has a list of tags, SnSTopic, we'll deliver an sns message for
            any resources with SnSTopic set with a value that is a valid sns topic.
        """

        self.log.info("Downloading messages from the SQS queue.")

        sqs_messages = MailerSqsQueueIterator(self.sqs, self.receive_queue)
        sqs_messages.msg_attributes = ['mtype', 'recipient']

        with ParallelSQSProcessor(parallel, sqs_messages) as ParallelProcessor:
            for sqs_message in sqs_messages:
                ParallelProcessor(self.process_sqs_message(encoded_sqs_message=sqs_message))
        return
