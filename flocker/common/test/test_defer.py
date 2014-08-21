from twisted.trial.unittest import TestCase

class LogAndReturnFailureTests(TestCase):
    """
    Tests for ``_twisted._log_and_return_failure`` .
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
    Tests for ``_twisted.gather_deferreds``
    """
    def test_consume_errors_default(self):
        """
        If there are errbacks in the supplied ``Deferred``s they are unhandled
        by default.
        """

    def test_consume_errors_true(self):
        """
        If ``consumeErrors`` is ``True`` the unhandled errbacks in the supplied
        ``Deferred``s are handled.
        """

    def test_no_logging(self):
        """
        If ``errorLogger`` is ``None``, none of the failures are logged.
        """

    def test_default_logger(self):
        """
        ``errorLogger`` is ``twisted.python.log.err`` by default.
        """

    def test_error_logger_overrride(self):
        """
        If a customer ``errorLogger`` is supplied, it is called once for each
        failure in the supplied ``Deferred``s.
        """
