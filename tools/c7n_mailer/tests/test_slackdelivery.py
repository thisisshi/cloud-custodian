import logging
import boto3

from c7n_mailer.slack_delivery import SlackDelivery

from common import SAMPLE_SLACK_SQS_MESSAGE, MAILER_REAL_QUEUE_CONFIG
from test_email import EmailTest
from test_sqs_processor import MockMailerSqsQueueProcessor


class SlackDeliveryTest(EmailTest):
    def test_slack_get_to_addrs_sans_user_retrieval(self):

        processor = MockMailerSqsQueueProcessor(
            config=MAILER_REAL_QUEUE_CONFIG,
            session=boto3.Session(),
            max_num_processes=4
        )

        sqs_message = processor.unpack_sqs_message(SAMPLE_SLACK_SQS_MESSAGE)

        slack_delivery = SlackDelivery('faketoken', 'fakewebhook', None, self.email_delivery)
        results = slack_delivery.get_to_addrs_slack_messages_map(sqs_message)

        self.assertTrue(results)

        # policy specified three slack targets and 1 email so we should get 3 back:
        #
        # policies:
        #   - name: s3
        #     resource: s3
        #     actions:
        #       - type: notify
        #         template: default
        #         subject: test
        #         to:
        #           - hello@example.com
        #           - https://hooks.slack.com/foo
        #           - slack://webhook/#foo
        #           - slack://#foo
        #         transport:
        #           type: sqs
        #           queue: https://sqs.us-east-1.amazonaws.com/644160558196/c7n-mailer-test-queue

        self.assertTrue(len(results), 3)

        self.assertTrue(results['fakewebhook'])
        self.assertTrue(results['foo'])
        self.assertTrue(results['https://hooks.slack.com/foo'])


class MockClass(object):
    def __init__(self):
        self.log = logging.getLogger('foo')
