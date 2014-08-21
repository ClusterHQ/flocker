from twisted.trial.unittest import TestCase

class LogAndReturnFailureTests(TestCase):
    """
    Tests for ``_log_and_return_failure``.
    """
    def test_failure_logged(self):
        """
        The supplied failure is logged.
        """

    def test_default_logger(self):
        """
        The default logger is twisted.python.log.err
        """

    def test_failure_returned(self):
        """
        The supplied failure is returned.
        """


class GatherDeferredsTests(TestCase):
    """
    Tests for ``gather_deferreds``.
    """
    def test_consume_errors_true(self):
        """
        The unhandled errbacks in the supplied ``Deferred``s are handled.
        """

    def test_fire_on_first_failure(self):
        """
        The first errback in the supplied list of deferreds causes the returned
        deferred to errback with that failure.
        """

    def test_logging(self):
        """
        Failures in the supplied deferreds are logged.
        """
