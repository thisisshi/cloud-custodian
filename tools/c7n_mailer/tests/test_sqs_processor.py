import boto3
import os
import placebo

from mock import patch
from unittest import TestCase

from c7n_mailer.ldap_lookup import Redis, LocalSqlite, LdapLookup
from c7n_mailer.email_delivery import EmailDelivery
from c7n_mailer.sns_delivery import SnsDelivery
from c7n_mailer.sqs_queue_processor import ParallelSQSProcessor, \
    MailerSqsQueueIterator, MailerSqsQueueProcessor

from common import MAILER_CONFIG, MAILER_REDIS_CONFIG, MAILER_NO_CACHE_CONFIG, \
    MAILER_REAL_QUEUE_CONFIG, get_fake_ldap_connection, MockRedisLookup, \
    MockLocalSqlite, SAMPLE_SQS_MESSAGE

DIR_NAME = os.path.dirname(os.path.realpath(__file__))


class TestParallelSqsProcessor(TestCase):
    def test_parallel_processor_context_manager(self):
        parallel_false = ParallelSQSProcessor(parallel=False, max_num_processes=0, sqs_messages=[])
        with parallel_false:
            # multiprocessing may be imported from another project during testing
            self.assertFalse(parallel_false.multiprocessing)
            self.assertFalse(parallel_false.parallel)
            self.assertFalse(hasattr(parallel_false, 'process_pool'))

        parallel_true = ParallelSQSProcessor(parallel=True, max_num_processes=2, sqs_messages=[])
        with parallel_true:
            self.assertTrue(parallel_true.multiprocessing)
            self.assertTrue(parallel_true.parallel)
            self.assertTrue(hasattr(parallel_true, 'process_pool'))

    def test_parallel_processor_decorator_true(self):
        # assert messages are being added to the process pool
        # assert messages are being ack'd
        pass

    def test_parallel_processor_decorator_false(self):
        # assert function is being called
        # assert messages are being ack'd
        pass


class TestMailerSqsQueueIterator(TestCase):
    def test_sqs_queue_iterate(self):
        # TODO: use vcr or placebo to record these interactions and place the
        # results in cassettes directory

        session = boto3.Session(region_name='us-east-1')
        pill = placebo.attach(session, data_path=DIR_NAME + '/data/test_sqs_queue_iterate')
        pill.playback()

        client = session.client('sqs', 'us-east-1')

        iterator = MailerSqsQueueIterator(
            aws_sqs=client,
            queue_url='https://sqs.us-east-1.amazonaws.com/644160558196/c7n-mailer-test-queue',
            limit=1,
            timeout=1
        )

        for i in iterator:
            msg = i

        self.assertTrue(msg)


class TestMailerSqsQueueProcessor(TestCase):
    def test_sqs_queue_processor(self):
        processor = MockMailerSqsQueueProcessor(
            config=MAILER_CONFIG,
            session=boto3.Session(region_name='us-east-1'),
            max_num_processes=1
        )
        self.assertTrue(processor)

        # assert that ldap connections are created if they exist in config
        self.assertTrue(MAILER_CONFIG['ldap_uri'])
        self.assertTrue(processor.ldap_lookup)
        self.assertFalse(isinstance(processor.ldap_lookup, LdapLookup))

        # assert that cache connections are created if they exist in config
        self.assertEqual(MAILER_CONFIG['cache_engine'], 'sqlite')
        self.assertTrue(isinstance(processor.cache_engine, MockLocalSqlite))

        # assert that email and sns delivery instances are created on init
        self.assertTrue(isinstance(processor.email_delivery, EmailDelivery))
        self.assertTrue(isinstance(processor.sns_delivery, SnsDelivery))

    def test_sqs_queue_processor_get_cache_engine_sqlite(self):
        processor = MockLdapMailerSqsQueueProcessor(
            config=MAILER_CONFIG,
            session=boto3.Session(region_name='us-east-1'),
            max_num_processes=1
        )
        self.assertTrue(processor.cache_engine)
        self.assertTrue(isinstance(processor.cache_engine, LocalSqlite))

    def test_sqs_queue_processor_get_cache_engine_redis(self):
        processor = MockLdapMailerSqsQueueProcessor(
            config=MAILER_REDIS_CONFIG,
            session=boto3.Session(region_name='us-east-1'),
            max_num_processes=1
        )
        self.assertTrue(processor.cache_engine)
        self.assertTrue(isinstance(processor.cache_engine, Redis))

    def test_sqs_queue_processor_get_cache_engine_none(self):
        processor = MockLdapMailerSqsQueueProcessor(
            config=MAILER_NO_CACHE_CONFIG,
            session=boto3.Session(region_name='us-east-1'),
            max_num_processes=1
        )
        self.assertTrue(processor.cache_engine is None)

    def test_sqs_queue_processor_unpack_message(self):
        processor = MockLdapMailerSqsQueueProcessor(
            config=MAILER_NO_CACHE_CONFIG,
            session=boto3.Session(region_name='us-east-1'),
            max_num_processes=1
        )
        self.assertTrue(processor.cache_engine is None)
        unpacked = processor.unpack_sqs_message(SAMPLE_SQS_MESSAGE)
        self.assertTrue(unpacked)
        self.assertTrue(unpacked['policy'])
        self.assertTrue(unpacked['resources'])
        self.assertTrue(unpacked['action'])

    def test_sqs_queue_processor_process_message(self):
        processor = MockLdapMailerSqsQueueProcessor(
            config=MAILER_NO_CACHE_CONFIG,
            session=boto3.Session(region_name='us-east-1'),
            max_num_processes=1
        )
        with patch("smtplib.SMTP") as mock_smtp:
            self.assertTrue(processor.process_sqs_message(SAMPLE_SQS_MESSAGE))
            smtp_instance = mock_smtp.return_value
            self.assertTrue(smtp_instance.sendmail.called)
            self.assertEqual(smtp_instance.sendmail.call_count, 1)

    def test_sqs_queue_processor_run(self):
        session = boto3.Session(region_name='us-east-1')
        pill = placebo.attach(session, data_path=DIR_NAME + '/data/test_sqs_queue_processor_run')
        pill.playback()

        processor = MockLdapMailerSqsQueueProcessor(
            config=MAILER_REAL_QUEUE_CONFIG,
            session=session,
            max_num_processes=4
        )

        with patch("smtplib.SMTP") as mock_smtp:
            result = processor.run(parallel=False)
            smtp_instance = mock_smtp.return_value
            self.assertTrue(smtp_instance.sendmail.called)
            self.assertTrue(result)


class MockLdapMailerSqsQueueProcessor(MailerSqsQueueProcessor):
    def get_ldap_lookup(self, *args, **kwargs):
        return get_fake_ldap_connection()


class MockMailerSqsQueueProcessor(MockLdapMailerSqsQueueProcessor, MailerSqsQueueProcessor):
    def get_cache_engine(self, cache_engine, redis_host, redis_port, ldap_cache_file):
        engine = super(MockMailerSqsQueueProcessor, self).get_cache_engine(
            cache_engine, redis_host, redis_port, ldap_cache_file)

        if isinstance(engine, Redis):
            return MockRedisLookup(redis_host, redis_port=redis_port, db=-1)
        elif isinstance(engine, LocalSqlite):
            return MockLocalSqlite(ldap_cache_file)
        else:
            return None
