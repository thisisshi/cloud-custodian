# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class TestTimestreamDatabase(BaseTest):
    def test_timestream_database_tag(self):
        session_factory = self.replay_flight_data('test_timestream_database_tag')
        p = self.load_policy(
            {
                'name': 'test-timestream-db-tag',
                'resource': 'aws.timestream-database',
                'filters': [
                    {
                        'tag:foo': 'absent'
                    }
                ],
                'actions': [
                    {
                        'type': 'tag',
                        'tags': {'foo': 'bar'}
                    }
                ]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('timestream-write')
        tags = client.list_tags_for_resource(ResourceARN=resources[0]['Arn'])['Tags']
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0]['Key'], 'foo')
        self.assertEqual(tags[0]['Value'], 'bar')

    def test_timestream_database_remove_tag(self):
        session_factory = self.replay_flight_data('test_timestream_database_remove_tag')
        p = self.load_policy(
            {
                'name': 'test-timestream-db-tag',
                'resource': 'aws.timestream-database',
                'filters': [
                    {
                        'tag:foo': 'present'
                    }
                ],
                'actions': [
                    {
                        'type': 'remove-tag',
                        'tags': ['foo']
                    }
                ]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('timestream-write')
        tags = client.list_tags_for_resource(ResourceARN=resources[0]['Arn'])['Tags']
        self.assertEqual(len(tags), 0)


class TestTimestreamTable(BaseTest):
    def test_timestream_table_tag(self):
        session_factory = self.replay_flight_data('test_timestream_table_tag')
        p = self.load_policy(
            {
                'name': 'test-timestream-table-tag',
                'resource': 'aws.timestream-table',
                'filters': [
                    {
                        'tag:foo': 'absent'
                    }
                ],
                'actions': [
                    {
                        'type': 'tag',
                        'tags': {'foo': 'bar'}
                    }
                ]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('timestream-write')
        tags = client.list_tags_for_resource(ResourceARN=resources[0]['Arn'])['Tags']
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0]['Key'], 'foo')
        self.assertEqual(tags[0]['Value'], 'bar')

    def test_timestream_table_remove_tag(self):
        session_factory = self.replay_flight_data('test_timestream_table_remove_tag')
        p = self.load_policy(
            {
                'name': 'test-timestream-table-tag',
                'resource': 'aws.timestream-table',
                'filters': [
                    {
                        'tag:foo': 'present'
                    }
                ],
                'actions': [
                    {
                        'type': 'remove-tag',
                        'tags': ['foo']
                    }
                ]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('timestream-write')
        tags = client.list_tags_for_resource(ResourceARN=resources[0]['Arn'])['Tags']
        self.assertEqual(len(tags), 0)
