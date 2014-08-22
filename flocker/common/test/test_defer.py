from .._defer import GatherDeferredsAPI, gather_deferreds

from twisted.internet.defer import fail, FirstError, succeed
from twisted.python import log
from twisted.python.failure import Failure
from twisted.trial.unittest import TestCase


class GatherDeferredsTests(TestCase):
    """
    Tests for ``gather_deferreds``.
    """
    def test_gather_deferreds_api(self):
        """
        ``gather_deferreds`` is ``GatherDeferredsAPI.gather_deferreds``.
        """
        self.assertIs(
            GatherDeferredsAPI.gather_deferreds.__func__,
            gather_deferreds.__func__
        )

    def test_success(self):
        """
        The successful results of the supplied ``Deferred``s are returned.
        """
        expected_result1 = object()
        expected_result2 = object()

        d = GatherDeferredsAPI(log_errors=False).gather_deferreds(
            [succeed(expected_result1), succeed(expected_result2)])

        results = self.successResultOf(d)
        self.assertEqual([expected_result1, expected_result2], results)

    def test_consume_errors_true(self):
        """
        The unhandled errbacks in the supplied ``Deferred``s are handled.
        """
        d = GatherDeferredsAPI(log_errors=False).gather_deferreds(
            [fail(ZeroDivisionError('test_consume_errors1')),
             fail(ZeroDivisionError('test_consume_errors2'))])

        self.failureResultOf(d, FirstError)
        self.assertEqual([], self.flushLoggedErrors(ZeroDivisionError))

    def test_fire_on_first_failure(self):
        """
        The first errback in the supplied list of deferreds causes the returned
        deferred to errback with that failure.
        """
        expected_error = ZeroDivisionError('test_fire_on_first_failure1')
        d = GatherDeferredsAPI(log_errors=False).gather_deferreds(
            [fail(expected_error),
             fail(ZeroDivisionError('test_fire_on_first_failure2'))])

        failure = self.failureResultOf(d, FirstError)
        self.assertEqual(expected_error, failure.value.subFailure.value)

    def test_logging(self):
        """
        Failures in the supplied deferreds are all logged.
        """
        messages = []
        log.addObserver(messages.append)
        self.addCleanup(log.removeObserver, messages.append)
        expected_failure1 = Failure(ZeroDivisionError('test_logging1'))
        expected_failure2 = Failure(ZeroDivisionError('test_logging2'))

        d = GatherDeferredsAPI(log_errors=True).gather_deferreds(
            [fail(expected_failure1), fail(expected_failure2)])

        self.failureResultOf(d, FirstError)
        self.assertEqual(
            [expected_failure1, expected_failure2],
            self.flushLoggedErrors(ZeroDivisionError)
        )
