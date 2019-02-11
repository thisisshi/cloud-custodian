import logging

from c7n_mailer.slack_delivery import SlackDelivery
from c7n_mailer.sqs_queue_processor import MailerSqsQueueProcessor

from common import SAMPLE_SLACK_SQS_MESSAGE
from test_email import EmailTest


class SlackDeliveryTest(EmailTest):
    def test_slack_get_to_addrs_sans_user_retrieval(self):
        sqs_message = MailerSqsQueueProcessor.unpack_sqs_message(
            MockClass(), SAMPLE_SLACK_SQS_MESSAGE)

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
        breakpoint()


class MockClass(object):
    def __init__(self):
        self.log = logging.getLogger('foo')
