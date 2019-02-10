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
import logging
import six
import smtplib

from smtplib import SMTPHeloError, SMTPException, SMTPAuthenticationError

from email.mime.text import MIMEText
from itertools import chain

from c7n_mailer.utils_email import is_email
from .utils import (
    format_struct, get_message_subject, get_resource_tag_targets,
    get_rendered_jinja)


class EmailDelivery(object):

    # Those headers are defined as follows:
    #  'X-Priority': 1 (Highest), 2 (High), 3 (Normal), 4 (Low), 5 (Lowest)
    #              Non-standard, cf https://people.dsv.su.se/~jpalme/ietf/ietf-mail-attributes.html
    #              Set by Thunderbird
    #  'X-MSMail-Priority': High, Normal, Low
    #              Cf Microsoft https://msdn.microsoft.com/en-us/library/gg671973(v=exchg.80).aspx
    #              Note: May increase SPAM level on Spamassassin:
    #                    https://wiki.apache.org/spamassassin/Rules/MISSING_MIMEOLE
    #  'Priority': "normal" / "non-urgent" / "urgent"
    #              Cf https://tools.ietf.org/html/rfc2156#section-5.3.6
    #  'Importance': "low" / "normal" / "high"
    #              Cf https://tools.ietf.org/html/rfc2156#section-5.3.4

    PRIORITIES = {
        '1': {
            'X-Priority': '1 (Highest)',
            'X-MSMail-Priority': 'High',
            'Priority': 'urgent',
            'Importance': 'high',
        },
        '2': {
            'X-Priority': '2 (High)',
            'X-MSMail-Priority': 'High',
            'Priority': 'urgent',
            'Importance': 'high',
        },
        '3': {
            'X-Priority': '3 (Normal)',
            'X-MSMail-Priority': 'Normal',
            'Priority': 'normal',
            'Importance': 'normal',
        },
        '4': {
            'X-Priority': '4 (Low)',
            'X-MSMail-Priority': 'Low',
            'Priority': 'non-urgent',
            'Importance': 'low',
        },
        '5': {
            'X-Priority': '5 (Lowest)',
            'X-MSMail-Priority': 'Low',
            'Priority': 'non-urgent',
            'Importance': 'low',
        }
    }

    def __init__(self, session, ldap_lookup, org_domain, contact_tags, account_emails,
            templates_folders, from_address, ldap_uid_tag_keys, smtp_server,
            smtp_port, smtp_ssl, smtp_username, smtp_password, ses_region, *args, **kwargs):
        self.log = logging.getLogger(__name__)
        self.session = session

        self.ldap_lookup = ldap_lookup

        self.org_domain = org_domain
        self.contact_tags = contact_tags
        self.account_emails = account_emails
        self.templates_folders = templates_folders
        self.from_address = from_address
        self.ldap_uid_tag_keys = ldap_uid_tag_keys

        self.smtp_server = smtp_server

        if not self.smtp_server:
            # only insantiate a new client if mailer is sending via SES
            # this should allow for compatibility with other cloud providers
            # to send email via SMTP
            self.aws_ses = session.client('ses', region_name=ses_region)
        else:
            self.smtp_port = smtp_port
            self.smtp_ssl = smtp_ssl
            self.smtp_username = smtp_username
            self.smtp_password = smtp_password

    def get_event_owner_email(self, targets, event):
        """
        Returns a list of event owner email addresses from an event
        """

        if 'event-owner' not in targets:
            return []

        aws_username = self.get_aws_username_from_event(event)

        if aws_username:
            if is_email(aws_username):
                # is using SSO, the target might already be an email
                return [aws_username]
            elif self.ldap_lookup:
                # if the LDAP config is set, lookup in ldap
                return self.ldap_lookup.get_email_to_addrs_from_uid(aws_username)
            elif self.org_domain:
                # the org_domain setting is configured, append the org_domain
                # to the username from AWS
                self.log.info('adding email %s to targets.', aws_username + '@' + self.org_domain)
                return [aws_username + '@' + self.org_domain]
            else:
                self.log.warning(
                    'Unable to lookup event owner email. Please configure LDAP or org_domain')
        else:
            self.log.info('No AWS username in event')

        return []

    def get_ldap_emails_from_resource(self, sqs_message, resource):
        """
        Return a list of ldap emails from resource
        """

        if not self.ldap_lookup or not self.ldap_uid_tag_keys:
            return []

        # this whole section grabs any ldap uids (including manager emails if option is on)
        # and gets the emails for them and returns an array with all the emails
        ldap_uid_tag_values = get_resource_tag_targets(resource, self.ldap_uid_tag_keys)
        email_manager = sqs_message['action'].get('email_ldap_username_manager', False)
        ldap_uid_emails = []
        # some types of resources, like iam-user have 'Username' in the resource, if the policy
        # opted in to resource_ldap_lookup_username: true, we'll do a lookup and send an email
        if sqs_message['action'].get('resource_ldap_lookup_username'):
            ldap_uid_emails.extend(
                self.ldap_lookup.get_email_to_addrs_from_uid(
                    resource.get('UserName'), manager=email_manager))
        for ldap_uid_tag_value in ldap_uid_tag_values:
            ldap_uid_emails.extend(
                self.ldap_lookup.get_email_to_addrs_from_uid(
                    ldap_uid_tag_value, manager=email_manager))
        return ldap_uid_emails

    def get_resource_owner_emails_from_resource(self, sqs_message, resource):
        """
        Return a list of resource owner email addresses from the resource
        """
        if 'resource-owner' not in sqs_message['action']['to']:
            return []

        resource_owner_tag_keys = self.contact_tags
        resource_owner_tag_values = get_resource_tag_targets(resource, resource_owner_tag_keys)
        explicit_emails = [e for e in resource_owner_tag_values if is_email(e)]

        # resolve the contact info from ldap
        non_email_ids = list(set(resource_owner_tag_values).difference(explicit_emails))
        ldap_emails = list(
            chain.from_iterable(
                [self.ldap_lookup.get_email_to_addrs_from_uid(uid) for uid in non_email_ids]
            )
        )

        return list(chain(explicit_emails, ldap_emails))

    def get_account_emails(self, sqs_message):
        """
        Returns a list of emails based on the account id
        """

        if 'account-emails' not in sqs_message['action']['to']:
            return []

        email_list = []

        account_id = sqs_message.get('account_id', None)
        self.log.debug('get_account_emails for account_id: %s.', account_id)

        if account_id is not None:
            self.log.debug(
                'get_account_emails account_email_mapping: %s.', self.account_emails)
            email_list = self.account_emails.get(account_id, [])
            self.log.debug('get_account_emails email_list: %s.', email_list)

        return [e for e in email_list if is_email(e)]

    def get_email_to_addrs_to_resources_map(self, sqs_message):
        """
        Returns a dictionary with a tuple of emails as the key and the
        list of resources as the value.

        i.e. {(emails): [resources]}

        This helps ensure minimal emails are sent, while only ever
        sending emails to the respective parties.
        """

        email_to_addrs_to_resources_map = {}

        targets = sqs_message['action']['to'] + sqs_message['action'].get('cc', [])
        no_owner_targets = [e for e in
            sqs_message['action'].get('owner_absent_contact', []) if is_email(e)]

        # static_emails: emails from the 'to' or 'cc' section in the notify action
        static_emails = [e for e in targets if is_email(e)]
        event_owner_email = self.get_event_owner_email(targets, sqs_message['event'])
        account_emails = self.get_account_emails(sqs_message)

        static_emails.extend(event_owner_email + account_emails)
        for resource in sqs_message['resources']:
            # resource_emails: list of emails applicable to the resource
            resource_addrs = []
            resource_addrs.extend(static_emails)
            resource_addrs.extend(self.get_ldap_emails_from_resource(sqs_message, resource))

            owner_addrs = self.get_resource_owner_emails_from_resource(sqs_message, resource)

            if owner_addrs:
                resource_addrs.extend(owner_addrs)
            else:
                if no_owner_targets:
                    resource_addrs.extend(no_owner_targets)

            # we allow multiple emails from various places, we'll unique with set to not have any
            # duplicates, and we'll also sort it so we always have the same key for other resources
            # and finally we'll make it a tuple, since that is hashable and can be a key in a dict
            resource_addrs = tuple(sorted(set(resource_addrs)))

            if resource_addrs:
                email_to_addrs_to_resources_map.setdefault(resource_addrs, []).append(resource)

        if email_to_addrs_to_resources_map == {}:
            self.log.debug('Found no email addresses, sending no emails.')

        return email_to_addrs_to_resources_map

    def get_to_addrs_email_messages_map(self, sqs_message):
        """
        Returns a mapping of email addresses to mimetext messages

        i.e. {(emails): mimetext_message}
        e.g. { ('milton@initech.com', 'peter@initech.com'): mimetext_message }
        """

        to_addrs_to_resources_map = self.get_email_to_addrs_to_resources_map(sqs_message)
        to_addrs_to_mimetext_map = {}

        for to_addrs, resources in six.iteritems(to_addrs_to_resources_map):
            to_addrs_to_mimetext_map[to_addrs] = self.get_mimetext_message(
                sqs_message,
                resources,
                list(to_addrs)
            )

        return to_addrs_to_mimetext_map

    def send_smtp_email(self, message, to_addrs):
        """
        Send mail via SMTP

        Configure SMTP server settings in the configuration file

        smtp_server
        smtp_port: default - 25
        smtp_ssl: default - True
        smtp_username
        smtp_password
        """

        connection = smtplib.SMTP(self.smtp_server, self.smtp_port)

        if self.smtp_ssl:
            try:
                # HELO is sent on smtp connection instantiation with starttls
                connection.starttls()
            except (SMTPHeloError, SMTPException) as e:
                self.log.error(
                    'Unable to initialize SSL connection with SMTP Server: %s' % e)
                raise e

        if self.smtp_username or self.smtp_password:
            try:
                connection.login(self.smtp_username, self.smtp_password)
            except (SMTPAuthenticationError, SMTPHeloError) as e:
                self.log.error('Unable to login to SMTP server: %s - %s' % (self.smtp_server, e))
                raise e

        connection.sendmail(message['From'], to_addrs, message.as_string())
        connection.quit()

    def set_mimetext_headers(self, message, subject, from_addr, to_addrs, cc_addrs, priority):
        """Returns a mimetext message with headers"""

        message['Subject'] = subject
        message['From'] = from_addr
        message['To'] = ', '.join(to_addrs)
        if cc_addrs:
            message['Cc'] = ', '.join(cc_addrs)

        if priority and priority in EmailDelivery.PRIORITIES.keys():
            priority = EmailDelivery.PRIORITIES[str(priority)].copy()
            for key in priority:
                message[key] = priority[key]

        return message

    def get_mimetext_message(self, sqs_message, resources, to_addrs):
        """
        Returns a Mimetext message, rendered with the template
        specified by the policy or a default template, and including
        all applicable headers
        """

        body = get_rendered_jinja(
            to_addrs, sqs_message, resources, 'template', 'default', self.templates_folders)

        if not body:
            return None

        email_format = sqs_message['action'].get('template_format', None)
        if not email_format:
            email_format = sqs_message['action'].get(
                'template', 'default').endswith('html') and 'html' or 'plain'

        message = self.set_mimetext_headers(
            message=MIMEText(body, email_format, 'utf-8'),
            subject=get_message_subject(sqs_message),
            from_addr=sqs_message['action'].get('from', self.from_address),
            to_addrs=to_addrs,
            cc_addrs=sqs_message['action'].get('cc', []),
            priority=sqs_message['action'].get('priority_header', None),
        )

        return message

    def send_c7n_email(self, sqs_message, email_to_addrs, mimetext_msg):
        """
        Send c7n_email

        If smtp_server is specified in configuration, send via SMTP
        Otherwise send email via AWS SES
        """
        error = None
        if hasattr(self, 'aws_ses'):
            try:
                self.aws_ses.send_raw_email(RawMessage={'Data': mimetext_msg.as_string()})
            except self.aws_ses.exceptions.AccountSendingPaused as e:
                self.log.error('SES sending is paused, exiting')
                raise e
            except Exception as e:
                error = e
        else:
            try:
                self.send_smtp_email(message=mimetext_msg, to_addrs=email_to_addrs)
            except (SMTPAuthenticationError, SMTPException) as e:
                self.log.error('SMTP Server does not support TLS or Unable to authenticate to SMTP Server, exiting') # noqa
                raise e
            except Exception as e:
                error = e

        if error:
            self.log.warning(
                "Error policy:%s account:%s sending to:%s \n\n error: %s\n\n mailer.yml" % (
                    sqs_message['policy'],
                    sqs_message.get('account', ''),
                    email_to_addrs,
                    error
                )
            )
        else:
            self.log.info("Sending account:%s policy:%s %s:%s email:%s to %s" % (
                sqs_message.get('account', ''),
                sqs_message['policy']['name'],
                sqs_message['policy']['resource'],
                str(len(sqs_message['resources'])),
                sqs_message['action'].get('template', 'default'),
                email_to_addrs))

    def get_aws_username_from_event(self, event):
        """
        Returns AWS user from event

        https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-event-reference-user-identity.html
        """

        if event is None:
            return None

        identity = event.get('detail', {}).get('userIdentity', {})

        if not identity:
            self.log.warning("Could not get recipient from event \n %s" % (
                format_struct(event)))
            return None

        if identity['type'] == 'AssumedRole':
            self.log.debug(
                'In some cases there is no ldap uid is associated with AssumedRole: %s',
                identity['arn'])
            self.log.debug(
                'We will try to assume that identity is in the AssumedRoleSessionName')
            user = identity['arn'].rsplit('/', 1)[-1]
            if user is None or user.startswith('i-') or user.startswith('awslambda'):
                return None
            if ':' in user:
                user = user.split(':', 1)[-1]
            return user
        elif identity['type'] == 'IAMUser' or identity['type'] == 'WebIdentityUser':
            return identity['userName']
        if identity['type'] == 'Root':
            return None

        # this conditional is left here as a last resort, it should
        # be better documented with an example UserIdentity json
        if ':' in identity['principalId']:
            user_id = identity['principalId'].split(':', 1)[-1]
        else:
            user_id = identity['principalId']
        return user_id
