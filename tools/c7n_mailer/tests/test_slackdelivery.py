import boto3
import six

from c7n_mailer.slack_delivery import SlackDelivery

from common import SAMPLE_SLACK_SQS_MESSAGE, MAILER_REAL_QUEUE_CONFIG, \
    SAMPLE_SLACK_SQS_MESSAGE_WITH_LOOKUP, SAMPLE_SLACK_TO_ADDR_MESSAGE_MAP, \
    MailerVcr

from test_email import EmailTest
from test_sqs_processor import MockMailerSqsQueueProcessor


def unpack_message(message):
    processor = MockMailerSqsQueueProcessor(
        config=MAILER_REAL_QUEUE_CONFIG,
        session=boto3.Session(),
        max_num_processes=4
    )
    sqs_message = processor.unpack_sqs_message(message)
    return sqs_message


class SlackDeliveryTest(EmailTest):
    def test_slack_get_to_addrs_sans_user_retrieval(self):
        sqs_message = unpack_message(SAMPLE_SLACK_SQS_MESSAGE)

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

    @MailerVcr.use_cassette()
    def test_slack_get_to_addrs_with_user_lookup(self):
        # so my email doesn't get picked up by a bot crawling github...
        email = 't' + 'hel' + 'i@o' + 'utlook.com'
        sqs_message = unpack_message(SAMPLE_SLACK_SQS_MESSAGE_WITH_LOOKUP)
        slack_delivery = SlackDelivery('faketoken', 'fakewebhook', None, self.email_delivery)
        results = slack_delivery.get_to_addrs_slack_messages_map(sqs_message)
        # TODO - need to actually have assertions here
        self.assertTrue(results)
        self.assertTrue(len(results.keys()))
        self.assertTrue(email in results.keys())
        self.assertTrue(isinstance(results[email], list))
        self.assertTrue(len(results[email]))
        for m in results[email]:
            self.assertTrue(isinstance(m, six.string_types))

    @MailerVcr.use_cassette()
    def test_slack_send_message(self):
        slack_delivery = SlackDelivery('faketoken', 'fakewebhook', None, self.email_delivery)
        responses = []

        counter = 0

        for k, v in SAMPLE_SLACK_TO_ADDR_MESSAGE_MAP.items():
            for m in v:
                counter += 1

        for k, v in SAMPLE_SLACK_TO_ADDR_MESSAGE_MAP.items():
            for m in v:
                resp = slack_delivery.send_slack_msg(k, m)
                if resp:
                    responses.append(resp)

        self.assertTrue(responses)
        self.assertEqual(len(responses), counter)
        for r in responses:
            self.assertEqual(resp.status_code, 200)

    @MailerVcr.use_cassette()
    def test_slack_handler(self):
        slack_delivery = SlackDelivery('faketoken', 'fakewebhook', None, self.email_delivery)
        result = slack_delivery.slack_handler(SAMPLE_SLACK_TO_ADDR_MESSAGE_MAP)
        self.assertTrue(result)
