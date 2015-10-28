# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.testtools``.
"""

from subprocess import CalledProcessError

from eliot.testing import (
    capture_logging,
    LoggedAction, LoggedMessage,
    assertContainsFields,
)

from twisted.internet.defer import succeed
from twisted.trial.unittest import SynchronousTestCase
from twisted.internet.task import Clock
from twisted.python.failure import Failure

from flocker.testtools import (
    run_process,
    loop_until, LOOP_UNTIL_ACTION, LOOP_UNTIL_ITERATION_MESSAGE,
    LoopExceeded, retry_failure,
)


class RunProcessTests(SynchronousTestCase):
    """
    Tests for ``run_process``.
    """
    def _failing_shell(self, expression):
        """
        Construct an argument list which runs a child shell which evaluates the
        given expression and then exits with an error code.

        :param bytes expression: Some shell expression.

        :return: A ``list`` of ``bytes`` suitable to be passed to
            ``run_process``.
        """
        return [b"/bin/sh", b"-c", expression + b" && exec false"]

    def _run_fail(self, command):
        """
        Use ``run_process`` to run a child shell process which is expected to
        exit with an error code.

        :param list command: An argument list to use to launch the child
            process.

        :raise: A test-failing exception if ``run_process`` does not raise
            ``CalledProcessError``.

        :return: The ``CalledProcessError`` raised by ``run_process``.
        """
        exception = self.assertRaises(
            CalledProcessError,
            run_process,
            command,
        )
        return exception

    def test_on_error(self):
        """
        If the child process exits with a non-zero exit status, ``run_process``
        raises ``CalledProcessError`` initialized with the command, exit
        status, and any output.
        """
        command = self._failing_shell(b"echo goodbye")
        exception = self._run_fail(command)
        expected = (1, command, b"goodbye\n")
        actual = (
            exception.returncode, exception.cmd, exception.output
        )
        self.assertEqual(expected, actual)

    def test_exception_str(self):
        """
        The exception raised by ``run_process`` has a string representation
        that includes the output from the failed child process.
        """
        exception = self._run_fail(self._failing_shell(b"echo hello"))
        self.assertIn("hello", str(exception))


class LoopUntilTests(SynchronousTestCase):
    """
    Tests for :py:func:`loop_until`.
    """

    @capture_logging(None)
    def test_immediate_success(self, logger):
        """
        If the predicate returns something truthy immediately, then
        ``loop_until`` returns a deferred that has already fired with that
        value.
        """
        result = object()

        def predicate():
            return result
        clock = Clock()
        d = loop_until(predicate, reactor=clock)
        self.assertEqual(
            self.successResultOf(d),
            result)

        action = LoggedAction.of_type(logger.messages, LOOP_UNTIL_ACTION)[0]
        assertContainsFields(self, action.start_message, {
            'predicate': predicate,
        })
        assertContainsFields(self, action.end_message, {
            'action_status': 'succeeded',
            'result': result,
        })

    @capture_logging(None)
    def test_iterates(self, logger):
        """
        If the predicate returns something falsey followed by something truthy,
        then ``loop_until`` returns it immediately.
        """
        result = object()
        results = [None, result]

        def predicate():
            return results.pop(0)
        clock = Clock()

        d = loop_until(predicate, reactor=clock)

        self.assertNoResult(d)

        clock.advance(0.1)
        self.assertEqual(
            self.successResultOf(d),
            result)

        action = LoggedAction.of_type(logger.messages, LOOP_UNTIL_ACTION)[0]
        assertContainsFields(self, action.start_message, {
            'predicate': predicate,
        })
        assertContainsFields(self, action.end_message, {
            'result': result,
        })
        self.assertTrue(action.succeeded)
        message = LoggedMessage.of_type(
            logger.messages, LOOP_UNTIL_ITERATION_MESSAGE)[0]
        self.assertEqual(action.children, [message])
        assertContainsFields(self, message.message, {
            'result': None,
        })

    @capture_logging(None)
    def test_multiple_iterations(self, logger):
        """
        If the predicate returns something falsey followed by something truthy,
        then ``loop_until`` returns it immediately.
        """
        result = object()
        results = [None, False, result]
        expected_results = results[:-1]

        def predicate():
            return results.pop(0)
        clock = Clock()

        d = loop_until(predicate, reactor=clock)

        clock.advance(0.1)
        self.assertNoResult(d)
        clock.advance(0.1)

        self.assertEqual(
            self.successResultOf(d),
            result)

        action = LoggedAction.of_type(logger.messages, LOOP_UNTIL_ACTION)[0]
        assertContainsFields(self, action.start_message, {
            'predicate': predicate,
        })
        assertContainsFields(self, action.end_message, {
            'result': result,
        })
        self.assertTrue(action.succeeded)
        messages = LoggedMessage.of_type(
            logger.messages, LOOP_UNTIL_ITERATION_MESSAGE)
        self.assertEqual(action.children, messages)
        self.assertEqual(
            [messages[0].message['result'], messages[1].message['result']],
            expected_results,
        )

    @capture_logging(None)
    def test_custom_time_steps(self, logger):
        """
        loop_until can be passed a generator of intervals to wait on.
        """
        result = object()
        results = [None, False, result]

        def predicate():
            return results.pop(0)
        clock = Clock()

        d = loop_until(predicate, reactor=clock, steps=[1, 2, 3])

        clock.advance(1)
        self.assertNoResult(d)
        clock.advance(1)
        self.assertNoResult(d)
        clock.advance(1)

        self.assertEqual(self.successResultOf(d), result)

    @capture_logging(None)
    def test_fewer_steps_than_repeats(self, logger):
        """
        loop_until can be given fewer steps than it needs for the predicate to
        return True. In that case, something something.
        """
        results = [False] * 5
        steps = [0.1] * 2

        def predicate():
            return results.pop(0)
        clock = Clock()

        d = loop_until(predicate, reactor=clock, steps=steps)

        clock.advance(0.1)
        self.assertNoResult(d)
        clock.advance(0.1)
        self.assertEqual(
            str(self.failureResultOf(d).value),
            str(LoopExceeded(predicate, False)))


class RetryFailureTests(SynchronousTestCase):
    """
    Tests for :py:func:`retry_failure`.
    """

    def test_immediate_success(self):
        """
        If the function returns a successful value immediately, then
        ``retry_failure`` returns a deferred that has already fired with that
        value.
        """
        result = object()

        def function():
            return result

        clock = Clock()
        d = retry_failure(function, reactor=clock)
        self.assertEqual(self.successResultOf(d), result)

    def test_iterates_once(self):
        """
        If the function fails at first and then succeeds, ``retry_failure``
        returns the success.
        """
        steps = [0.1]

        result = object()
        results = [Failure(ValueError("bad value")), succeed(result)]

        def function():
            return results.pop(0)

        clock = Clock()

        d = retry_failure(function, reactor=clock, steps=steps)
        self.assertNoResult(d)

        clock.advance(0.1)
        self.assertEqual(self.successResultOf(d), result)

    def test_multiple_iterations(self):
        """
        If the function fails multiple times and then succeeds,
        ``retry_failure`` returns the success.
        """
        steps = [0.1, 0.2]

        result = object()
        results = [
            Failure(ValueError("bad value")),
            Failure(ValueError("bad value")),
            succeed(result),
        ]

        def function():
            return results.pop(0)

        clock = Clock()

        d = retry_failure(function, reactor=clock, steps=steps)
        self.assertNoResult(d)

        clock.advance(0.1)
        self.assertNoResult(d)

        clock.advance(0.1)
        self.assertNoResult(d)

        clock.advance(0.1)
        self.assertEqual(self.successResultOf(d), result)

    def test_too_many_iterations(self):
        """
        If ``retry_failure`` fails more times than there are steps provided, it
        errors back with the last failure.
        """
        steps = [0.1]

        result = object()
        failure = Failure(ValueError("really bad value"))

        results = [
            Failure(ValueError("bad value")),
            failure,
            succeed(result),
        ]

        def function():
            return results.pop(0)

        clock = Clock()

        d = retry_failure(function, reactor=clock, steps=steps)
        self.assertNoResult(d)

        clock.advance(0.1)
        self.assertEqual(self.failureResultOf(d), failure)

    def test_no_steps(self):
        """
        Calling ``retry_failure`` with an empty iterator for ``steps`` is the
        same as wrapping the function in ``maybeDeferred``.
        """
        steps = []

        result = object()
        failure = Failure(ValueError("really bad value"))

        results = [
            failure,
            succeed(result),
        ]

        def function():
            return results.pop(0)

        clock = Clock()

        d = retry_failure(function, reactor=clock, steps=steps)
        self.assertEqual(self.failureResultOf(d), failure)

    def test_limited_exceptions(self):
        """
        By default, ``retry_failure`` retries on any exception. However, if
        it's given an iterable of expected exception types (exactly as one
        might pass to ``Failure.check``), then it will only retry if one of
        *those* exceptions is raised.
        """
        steps = [0.1, 0.2]

        result = object()
        type_error = Failure(TypeError("bad type"))

        results = [
            Failure(ValueError("bad value")),
            type_error,
            succeed(result),
        ]

        def function():
            return results.pop(0)

        clock = Clock()

        d = retry_failure(
            function, expected=[ValueError], reactor=clock, steps=steps)
        self.assertNoResult(d)

        clock.advance(0.1)
        self.assertEqual(self.failureResultOf(d), type_error)
