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
import fakeredis
import logging
import os

from c7n_mailer.ldap_lookup import LdapLookup, Redis, LocalSqlite
from ldap3 import Server, Connection, MOCK_SYNC
from ldap3.strategy import mockBase

logger = logging.getLogger('custodian.mailer')

SAMPLE_SQS_MESSAGE = {
    'MessageId': '859a51c2-047e-43d6-951b-f0cd226ecb1a',
    'ReceiptHandle': 'AQEBvk0BH26/2dkKfBvsmYZuGcag3h8/vSGW+S6lI9c6QE26TA0kDmvAyv7OYaqYKDl3xn8GUx+wwIxFF8prdSUEull51AWZ9F7K3Qo/rHrHBZeD5CKXSTashrbukcApcXvmaMlFAglnlUa+aNsH8N+h50U8Cq0ObIFhKZxpw51CsKqpWLJkWRXlxnAHw41bDdbP2vYlW/4TmKu73MT+0Ja9qcAHm7ScAQk6xWOwO0GaPDCk9twM/y3Sk56Vp/yb6T0BbIJ756HRvJxuRam+JioaPHLaIO5mpkS1mHbxQsuMpQx0ULu52W/xU+UL/HZ3YdQUg+DkQpsShituSnLKD5qDFPGl4ZKc+TFFZiXe6WP8XjrqOQlK/jb6ege8E0wPN0CNams9BqfJdolzBpnYUyC1sg==', # noqa
    'MD5OfBody': '7e267d3c76cc1b937ab16b614575aa15',
    'Body': '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' # noqa
}

PETER = (
    'uid=peter,cn=users,dc=initech,dc=com',
    {
        'uid': ['peter'],
        'manager': 'uid=bill_lumbergh,cn=users,dc=initech,dc=com',
        'mail': 'peter@initech.com',
        'displayName': 'Peter',
        'objectClass': 'person'
    }
)
BILL = (
    'uid=bill_lumbergh,cn=users,dc=initech,dc=com',
    {
        'uid': ['bill_lumbergh'],
        'mail': 'bill_lumberg@initech.com',
        'displayName': 'Bill Lumberg',
        'objectClass': 'person'
    }
)

MAILER_CONFIG = {
    'smtp_port': 25,
    'from_address': 'devops@initech.com',
    'contact_tags': ['OwnerEmail', 'SupportEmail'],
    'queue_url': 'https://sqs.us-east-1.amazonaws.com/xxxx/cloudcustodian-mailer',
    'region': 'us-east-1',
    'ldap_uri': 'ldap.initech.com',
    'smtp_server': 'smtp.inittech.com',
    'cache_engine': 'sqlite',
    'role': 'arn:aws:iam::xxxx:role/cloudcustodian-mailer',
    'ldap_uid_tags': ['CreatorName', 'Owner'],
    'templates_folders': [os.path.abspath(os.path.dirname(__file__)),
                          os.path.abspath('/')],
}

MAILER_REDIS_CONFIG = {
    'smtp_port': 25,
    'from_address': 'devops@initech.com',
    'contact_tags': ['OwnerEmail', 'SupportEmail'],
    'queue_url': 'https://sqs.us-east-1.amazonaws.com/xxxx/cloudcustodian-mailer',
    'region': 'us-east-1',
    'ldap_uri': 'ldap.initech.com',
    'smtp_server': 'smtp.inittech.com',
    'cache_engine': 'redis',
    'redis_host': 'abc.com',
    'redis_port': '6379',
    'role': 'arn:aws:iam::xxxx:role/cloudcustodian-mailer',
    'ldap_uid_tags': ['CreatorName', 'Owner'],
    'templates_folders': [os.path.abspath(os.path.dirname(__file__)),
                          os.path.abspath('/')],
}

MAILER_NO_CACHE_CONFIG = {
    'smtp_port': 25,
    'from_address': 'devops@initech.com',
    'contact_tags': ['OwnerEmail', 'SupportEmail'],
    'queue_url': 'https://sqs.us-east-1.amazonaws.com/xxxx/cloudcustodian-mailer',
    'region': 'us-east-1',
    'ldap_uri': 'ldap.initech.com',
    'smtp_server': 'smtp.inittech.com',
    'role': 'arn:aws:iam::xxxx:role/cloudcustodian-mailer',
    'ldap_uid_tags': ['CreatorName', 'Owner'],
    'templates_folders': [os.path.abspath(os.path.dirname(__file__)),
                          os.path.abspath('/')],
}

MAILER_REAL_QUEUE_CONFIG = {
    'smtp_port': 25,
    'from_address': 'devops@initech.com',
    'contact_tags': ['OwnerEmail', 'SupportEmail'],
    'queue_url': 'https://sqs.us-east-1.amazonaws.com/644160558196/c7n-mailer-test-queue',
    'region': 'us-east-1',
    'ldap_uri': 'ldap.initech.com',
    'smtp_server': 'smtp.inittech.com',
    'role': 'arn:aws:iam::xxxx:role/cloudcustodian-mailer',
    'ldap_uid_tags': ['CreatorName', 'Owner'],
    'templates_folders': [os.path.abspath(os.path.dirname(__file__)),
                          os.path.abspath('/')],
}

MAILER_CONFIG_AZURE = {
    'queue_url': 'asq://storageaccount.queue.core.windows.net/queuename',
    'from_address': 'you@youremail.com',
    'sendgrid_api_key': 'SENDGRID_API_KEY',
    'templates_folders': [os.path.abspath(os.path.dirname(__file__)),
                          os.path.abspath('/')],
}

RESOURCE_1 = {
    'AvailabilityZone': 'us-east-1a',
    'Attachments': [],
    'Tags': [
        {
            'Value': 'milton@initech.com',
            'Key': 'SupportEmail'
        },
        {
            'Value': 'peter',
            'Key': 'CreatorName'
        }
    ],
    'VolumeId': 'vol-01a0e6ea6b89f0099'
}

RESOURCE_2 = {
    'AvailabilityZone': 'us-east-1c',
    'Attachments': [],
    'Tags': [
        {
            'Value': 'milton@initech.com',
            'Key': 'SupportEmail'
        },
        {
            'Value': 'peter',
            'Key': 'CreatorName'
        }
    ],
    'VolumeId': 'vol-21a0e7ea9b19f0043',
    'Size': 8
}

SQS_MESSAGE_1 = {
    'account': 'core-services-dev',
    'account_id': '000000000000',
    'region': 'us-east-1',
    'action': {
        'to': ['resource-owner', 'ldap_uid_tags'],
        'email_ldap_username_manager': True,
        'template': '',
        'priority_header': '1',
        'type': 'notify',
        'transport': {'queue': 'xxx', 'type': 'sqs'},
        'subject': '{{ account }} AWS EBS Volumes will be DELETED in 15 DAYS!'
    },
    'policy': {
        'filters': [{'Attachments': []}, {'tag:maid_status': 'absent'}],
        'resource': 'ebs',
        'actions': [
            {
                'type': 'mark-for-op',
                'days': 15,
                'op': 'delete'
            },
            {
                'to': ['resource-owner', 'ldap_uid_tags'],
                'email_ldap_username_manager': True,
                'template': '',
                'priority_header': '1',
                'type': 'notify',
                'subject': 'EBS Volumes will be DELETED in 15 DAYS!'
            }
        ],
        'comments': 'We are deleting your EBS volumes.',
        'name': 'ebs-mark-unattached-deletion'
    },
    'event': None,
    'resources': [RESOURCE_1]
}

SQS_MESSAGE_2 = {
    'account': 'core-services-dev',
    'account_id': '000000000000',
    'region': 'us-east-1',
    'action': {
        'type': 'notify',
        'to': ['datadog://?metric_name=EBS_volume.available.size']
    },
    'policy': {
        'filters': [{'Attachments': []}, {'tag:maid_status': 'absent'}],
        'resource': 'ebs',
        'actions': [
            {
                'type': 'mark-for-op',
                'days': 15,
                'op': 'delete'
            },
            {
                'type': 'notify',
                'to': ['datadog://?metric_name=EBS_volume.available.size']
            }
        ],
        'comments': 'We are deleting your EBS volumes.',
        'name': 'ebs-mark-unattached-deletion'
    },
    'event': None,
    'resources': [RESOURCE_1, RESOURCE_2]
}

SQS_MESSAGE_3 = {
    'account': 'core-services-dev',
    'account_id': '000000000000',
    'region': 'us-east-1',
    'action': {
        'type': 'notify',
        'to': ['datadog://?metric_name=EBS_volume.available.size&metric_value_tag=Size']
    },
    'policy': {
        'filters': [{'Attachments': []}, {'tag:maid_status': 'absent'}],
        'resource': 'ebs',
        'actions': [
            {
                'type': 'mark-for-op',
                'days': 15,
                'op': 'delete'
            },
            {
                'type': 'notify',
                'to': ['datadog://?metric_name=EBS_volume.available.size&metric_value_tag=Size']
            }
        ],
        'comments': 'We are deleting your EBS volumes.',
        'name': 'ebs-mark-unattached-deletion'
    },
    'event': None,
    'resources': [RESOURCE_2]
}

SQS_MESSAGE_4 = {
    'account': 'core-services-dev',
    'account_id': '000000000000',
    'region': 'us-east-1',
    'action': {
        'to': ['resource-owner', 'ldap_uid_tags'],
        'cc': ['hello@example.com', 'cc@example.com'],
        'email_ldap_username_manager': True,
        'template': 'default.html',
        'priority_header': '1',
        'type': 'notify',
        'transport': {'queue': 'xxx', 'type': 'sqs'},
        'subject': '{{ account }} AWS EBS Volumes will be DELETED in 15 DAYS!'
    },
    'policy': {
        'filters': [{'Attachments': []}, {'tag:maid_status': 'absent'}],
        'resource': 'ebs',
        'actions': [
            {
                'type': 'mark-for-op',
                'days': 15,
                'op': 'delete'
            },
            {
                'to': ['resource-owner', 'ldap_uid_tags'],
                'cc': ['hello@example.com', 'cc@example.com'],
                'email_ldap_username_manager': True,
                'template': 'default.html.j2',
                'priority_header': '1',
                'type': 'notify',
                'subject': 'EBS Volumes will be DELETED in 15 DAYS!'
            }
        ],
        'comments': 'We are deleting your EBS volumes.',
        'name': 'ebs-mark-unattached-deletion'
    },
    'event': None,
    'resources': [RESOURCE_1]
}

ASQ_MESSAGE = '''{
   "account":"subscription",
   "account_id":"ee98974b-5d2a-4d98-a78a-382f3715d07e",
   "region":"all",
   "action":{
      "to":[
         "user@domain.com"
      ],
      "template":"default",
      "priority_header":"2",
      "type":"notify",
      "transport":{
         "queue":"https://test.queue.core.windows.net/testcc",
         "type":"asq"
      },
      "subject":"testing notify action"
   },
   "policy":{
      "resource":"azure.keyvault",
      "name":"test-notify-for-keyvault",
      "actions":[
         {
            "to":[
               "user@domain.com"
            ],
            "template":"default",
            "priority_header":"2",
            "type":"notify",
            "transport":{
               "queue":"https://test.queue.core.windows.net/testcc",
               "type":"asq"
            },
            "subject":"testing notify action"
         }
      ]
   },
   "event":null,
   "resources":[
      {
         "name":"cckeyvault1",
         "tags":{

         },
         "resourceGroup":"test_keyvault",
         "location":"southcentralus",
         "type":"Microsoft.KeyVault/vaults",
         "id":"/subscriptions/ee98974b-5d2a-4d98-a78a-382f3715d07e/resourceGroups/test_keyvault/providers/Microsoft.KeyVault/vaults/cckeyvault1"
      }
   ]
}'''

ASQ_MESSAGE_TAG = '''{
   "account":"subscription",
   "account_id":"ee98974b-5d2a-4d98-a78a-382f3715d07e",
   "region":"all",
   "action":{
      "to":[
         "tag:owner"
      ],
      "template":"default",
      "priority_header":"2",
      "type":"notify",
      "transport":{
         "queue":"https://test.queue.core.windows.net/testcc",
         "type":"asq"
      },
      "subject":"testing notify action"
   },
   "policy":{
      "resource":"azure.keyvault",
      "name":"test-notify-for-keyvault",
      "actions":[
         {
            "to":[
               "tag:owner"
            ],
            "template":"default",
            "priority_header":"2",
            "type":"notify",
            "transport":{
               "queue":"https://test.queue.core.windows.net/testcc",
               "type":"asq"
            },
            "subject":"testing notify action"
         }
      ]
   },
   "event":null,
   "resources":[
      {
         "name":"cckeyvault1",
         "tags":{
            "owner":"user@domain.com"
         },
         "resourceGroup":"test_keyvault",
         "location":"southcentralus",
         "type":"Microsoft.KeyVault/vaults",
         "id":"/subscriptions/ee98974b-5d2a-4d98-a78a-382f3715d07e/resourceGroups/test_keyvault/providers/Microsoft.KeyVault/vaults/cckeyvault1"
      }
   ]
}'''


# Monkey-patch ldap3 to work around a bytes/text handling bug.

_safe_rdn = mockBase.safe_rdn


def safe_rdn(*a, **kw):
    return [(k, mockBase.to_raw(v)) for k, v in _safe_rdn(*a, **kw)]


mockBase.safe_rdn = safe_rdn


def get_fake_ldap_connection():
    server = Server('my_fake_server')
    connection = Connection(
        server,
        client_strategy=MOCK_SYNC
    )
    connection.bind()
    connection.strategy.add_entry(PETER[0], PETER[1])
    connection.strategy.add_entry(BILL[0], BILL[1])
    return connection


def get_ldap_lookup(cache_engine=None, uid_regex=None):
        if cache_engine == 'sqlite':
            cache_engine = MockLocalSqlite(':memory:')
        elif cache_engine == 'redis':
            cache_engine = MockRedisLookup(
                redis_host='localhost', redis_port=None)

        ldap_lookup = MockLdapLookup(
            ldap_uri=MAILER_CONFIG['ldap_uri'],
            ldap_bind_user='',
            ldap_bind_password='',
            ldap_bind_dn='cn=users,dc=initech,dc=com',
            ldap_email_key='mail',
            ldap_manager_attribute='manager',
            ldap_uid_attribute='uid',
            ldap_uid_regex=uid_regex,
            ldap_cache_file='',
            cache_engine=cache_engine
        )

        michael_bolton = {
            'dn': 'CN=Michael Bolton,cn=users,dc=initech,dc=com',
            'mail': 'michael_bolton@initech.com',
            'manager': 'CN=Milton,cn=users,dc=initech,dc=com',
            'displayName': 'Michael Bolton'
        }
        milton = {
            'uid': '123456',
            'dn': 'CN=Milton,cn=users,dc=initech,dc=com',
            'mail': 'milton@initech.com',
            'manager': 'CN=cthulhu,cn=users,dc=initech,dc=com',
            'displayName': 'Milton'
        }
        bob_porter = {
            'dn': 'CN=Bob Porter,cn=users,dc=initech,dc=com',
            'mail': 'bob_porter@initech.com',
            'manager': 'CN=Bob Slydell,cn=users,dc=initech,dc=com',
            'displayName': 'Bob Porter'
        }
        ldap_lookup.caching.set('michael_bolton', michael_bolton)
        ldap_lookup.caching.set(bob_porter['dn'], bob_porter)
        ldap_lookup.caching.set('123456', milton)
        ldap_lookup.caching.set(milton['dn'], milton)
        return ldap_lookup


class MockLdapLookup(LdapLookup):

    # us to instantiate this object and not have ldap3 try to connect
    # to anything or raise exception in unit tests, we replace connection with a mock
    def get_connection(self, ignore, these, params):
        return get_fake_ldap_connection()


class MockRedisLookup(Redis):
    def __init__(self, redis_host, redis_port):
        self.connection = fakeredis.FakeStrictRedis()


class MockLocalSqlite(LocalSqlite):
    pass
