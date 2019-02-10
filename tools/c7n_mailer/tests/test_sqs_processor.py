import boto3

from unittest import TestCase
from c7n_mailer.sqs_queue_processor import ParallelSQSProcessor, \
    MailerSqsQueueIterator, MailerSqsQueueProcessor

from common import MAILER_CONFIG


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

        client = boto3.client('sqs', 'us-east-1')

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
        processor = MailerSqsQueueProcessor(
            config=MAILER_CONFIG,
            session=boto3.Session(region_name='us-east-1'),
            max_num_processes=1
        )
        breakpoint()
        self.assertTrue(processor)
