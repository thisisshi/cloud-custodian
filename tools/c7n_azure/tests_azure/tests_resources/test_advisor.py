# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest
import pytest


@pytest.mark.skiplive
class AdvisorRecommendationTest(BaseTest):
    def test_azure_advisor_recommendation_schema_validate(self):
        p = self.load_policy({
            'name': 'test-azure-advisor-recommendations',
            'resource': 'azure.advisor-recommendation'
        }, validate=True)
        self.assertTrue(p)

    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-advisor-recommendation',
            'resource': 'azure.advisor-recommendation'
        })
        resources = p.run()
        self.assertTrue(len(resources) > 0)

    def test_advisor_recommendation_filter(self):
        p = self.load_policy({
            'name': 'test-azure-advisor-recommendation-filter',
            'resource': 'azure.disk',
            'filters': [
                {
                    'type': 'advisor-recommendation',
                    'key': '[].properties.category',
                    'value': 'Cost',
                    'value_type': 'swap',
                    'op': 'in'

                }
            ]
        })
        resources = p.run()
        self.assertTrue(len(resources) == 1)
        self.assertEqual(
            resources[0]['c7n:AdvisorRecommendation'],
            ['/subscriptions/ea42f556-5106-4743-99b0-c129bfa71a47/resourceGroups/JAMISON-POLICY-TESTING/providers/Microsoft.Compute/disks/JamisonsCMKDisk/providers/Microsoft.Advisor/recommendations/2e6e6212-2564-5654-5cad-ab783b685d2d']  # noqa
         )
