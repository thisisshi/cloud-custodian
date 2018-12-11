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

from .common import BaseTest


class TestFSx(BaseTest):
    def test_fsx_resource(self):
        session_factory = self.replay_flight_data('test_fsx_resource')
        p = self.load_policy(
            {
                'name': 'test-fsx',
                'resource': 'fsx',
                'filters': [
                    {
                        'tag:Name': 'test'
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertTrue(len(resources))

    def test_fsx_tag_resource(self):
        session_factory = self.replay_flight_data('test_fsx_tag_resource')
        p = self.load_policy(
            {
                'name': 'test-fsx',
                'resource': 'fsx',
                'filters': [
                    {
                        'tag:Name': 'test'
                    }
                ],
                'actions': [
                    {
                        'type': 'tag',
                        'key': 'test',
                        'value': 'test-value'
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertTrue(len(resources))
        client = session_factory().client('fsx')
        tags = client.list_tags_for_resource(ResourceARN=resources[0]['ResourceARN'])

        self.assertTrue([t for t in tags['Tags'] if t['Key'] == 'test'])

    def test_fsx_remove_tag_resource(self):
        session_factory = self.replay_flight_data('test_fsx_remove_tag_resource')
        p = self.load_policy(
            {
                'name': 'test-fsx',
                'resource': 'fsx',
                'filters': [
                    {
                        'tag:Name': 'test'
                    }
                ],
                'actions': [
                    {
                        'type': 'remove-tag',
                        'tags': [
                            'maid_status',
                            'test'
                        ],
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertTrue(len(resources))
        client = session_factory().client('fsx')
        tags = client.list_tags_for_resource(ResourceARN=resources[0]['ResourceARN'])

        self.assertFalse([t for t in tags['Tags'] if t['Key'] != 'Name'])

    def test_fsx_mark_for_op_resource(self):
        session_factory = self.replay_flight_data('test_fsx_mark_for_op_resource')
        p = self.load_policy(
            {
                'name': 'test-fsx',
                'resource': 'fsx',
                'filters': [
                    {
                        'tag:Name': 'test'
                    }
                ],
                'actions': [
                    {
                        'type': 'mark-for-op',
                        'op': 'tag'
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertTrue(len(resources))
        client = session_factory().client('fsx')
        tags = client.list_tags_for_resource(ResourceARN=resources[0]['ResourceARN'])

        self.assertTrue([t for t in tags['Tags'] if t['Key'] == 'maid_status'])
