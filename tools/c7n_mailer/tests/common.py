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
import vcr

from c7n_mailer.ldap_lookup import LdapLookup, Redis, LocalSqlite
from ldap3 import Server, Connection, MOCK_SYNC
from ldap3.strategy import mockBase

logger = logging.getLogger('custodian.mailer')

DIR_NAME = os.path.dirname(os.path.realpath(__file__))

SAMPLE_SQS_MESSAGE = {
    'MessageId': '859a51c2-047e-43d6-951b-f0cd226ecb1a',
    'ReceiptHandle': 'AQEBvk0BH26/2dkKfBvsmYZuGcag3h8/vSGW+S6lI9c6QE26TA0kDmvAyv7OYaqYKDl3xn8GUx+wwIxFF8prdSUEull51AWZ9F7K3Qo/rHrHBZeD5CKXSTashrbukcApcXvmaMlFAglnlUa+aNsH8N+h50U8Cq0ObIFhKZxpw51CsKqpWLJkWRXlxnAHw41bDdbP2vYlW/4TmKu73MT+0Ja9qcAHm7ScAQk6xWOwO0GaPDCk9twM/y3Sk56Vp/yb6T0BbIJ756HRvJxuRam+JioaPHLaIO5mpkS1mHbxQsuMpQx0ULu52W/xU+UL/HZ3YdQUg+DkQpsShituSnLKD5qDFPGl4ZKc+TFFZiXe6WP8XjrqOQlK/jb6ege8E0wPN0CNams9BqfJdolzBpnYUyC1sg==', # noqa
    'MD5OfBody': '7e267d3c76cc1b937ab16b614575aa15',
    'Body': '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' # noqa
}

SAMPLE_SLACK_SQS_MESSAGE = {
    'MessageId': 'cfefe159-2238-47de-9e5a-a5c1e18e889b',
    'ReceiptHandle': 'AQEBa+wVhkQnEmaeqc3pBtayA2thJzNTK8k3D6TsnLa7VQEcP2b06umHtR+I5U+3rbkW1U6CrXBZQt2t12jKqzRKr4mSIwEcUitPvKg4aLxXDKIxvVejk7BkIAogMNFBimYoE2mb1tS4GYV2RLLeOEw+59ukz3PUzEYP7WqIMVDwMOAj1uOMAa7kX75NelJz1yMP309yA1DXw+wwNeA2D0dZGkypCGia6AjqTGVXXwwN2aFPvogMrhOZas0IDdHdNxn4zD+5ItquAPJ8+/w9htuS3MfnLYNONp5BQv1X7BxuzYuguSg2ooEKpL7vUauMwrCkhiqpHEXgHXuouCCekvLK8UD74MaX26bX7mhgi4i+5M6hxUoSOsp1sq1mlm1FsRtXKf0AaE/yoY1vuVsbo334gw==', # noqa
    'MD5OfBody': '771643921fb11b23fe33b64005822c97',
    'Body': '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'} # noqa

SAMPLE_SLACK_SQS_MESSAGE_WITH_LOOKUP = {
    'MessageId': '86d5589c-ee53-482e-aea8-c32ecdef0b8d',
    'ReceiptHandle': 'AQEBY8NB4TrwxGMESvugA6nhzeVp7sQlnQIotpwktMV2XtvojMmZr1v3w577TS5IhRx5ng7D5BnbquWqPib90soW3unByVb0LXL2lNr2UFMgqoz7L5MXD3beuU5iIl8fFdeyCaoJm2h0L7cwxVrOLX4Ck0G/LjaUdui2vFsy7ag+qGP8NxNGVBgju7l/wfAu4h3B+cDjUcnizmj1LBjNRu1KrxnzzCeqhicJ+Ju2gjPGJFgxYCOiuVT+cF2OtzGhOTB2ksbonu2ZaEvhCwsoOFcmN62ZzZJiEGW9UtllW66IjhAU6Z2IZ122d4mprrUhXor14OnWWiCdGCWIhMrP8qQ0QWRBvhrkNNiO4h5DRZUhuJumBdqXROL7xL8vsYqA5xgedSsqQLPvlWjAjta8uUOsEA==', # noqa
    'MD5OfBody': 'e718f45dd95998843d776c824bd12956',
    'Body': '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' # noqa
}
SAMPLE_SLACK_TO_ADDR_MESSAGE_MAP = {'theli@outlook.com': ['{\n   "attachments":[\n      {\n         "fallback":"Cloud Custodian Policy Violation",\n         "author_name":"Cloud Custodian",\n         "title": "Policy Name: s3",\n         "color":"danger",\n         "fields":[\n            {\n               "title":"Account",\n               "value":"custodian-skunk-works",\n               "short":"True"\n            },\n            {\n               "title":"Region",\n               "value":"us-east-1",\n               "short":"True"\n            },{\n               "title":"Resources",\n               "value":"c7n-sagemaker-test\n"\n            }\n         ]\n      }\n   ],   "channel":"UG4A93HNK","username":"Cloud Custodian"\n}', '{\n   "attachments":[\n      {\n         "fallback":"Cloud Custodian Policy Violation",\n         "author_name":"Cloud Custodian",\n         "title": "Policy Name: s3",\n         "color":"danger",\n         "fields":[\n            {\n               "title":"Account",\n               "value":"custodian-skunk-works",\n               "short":"True"\n            },\n            {\n               "title":"Region",\n               "value":"us-east-1",\n               "short":"True"\n            },{\n               "title":"Resources",\n               "value":"aws-codestar-us-east-1-644160558196-c7n-test-pipe\nc7n-codebuild\nc7n-s3-orgid\nc7n-sagemaker-test\nc7n-ssm\nc7n-ssm-build\nc7n-test-bucket\nc7n-test-public-bucket\nc7n-test-s3-public-bucket\nc7n-vpc-flow-logs\ncf-templates-9c4kee3xbart-us-east-1\ncognito-vue\nconfig-bucket-644160558196\ncustodian-skunk-trails\nelasticbeanstalk-us-east-1-644160558196\ntest-for-global-accelerator-bucket\n"\n            }\n         ]\n      }\n   ],   "channel":"UG4A93HNK","username":"Cloud Custodian"\n}']} # noqa

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


def append_yaml(path):
    breakpoint()


MailerVcr = vcr.VCR(
    cassette_library_dir=DIR_NAME + '/data/cassettes/',
    match_on=['uri', 'method'],
    filter_headers=['authorization'],
    path_transformer=vcr.VCR.ensure_suffix('.yaml')
)
