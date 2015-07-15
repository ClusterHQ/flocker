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

from twisted.trial.unittest import SynchronousTestCase
from twisted.internet.task import Clock

from flocker.testtools import (
    run_process,
    loop_until, LOOP_UNTIL_ACTION, LOOP_UNTIL_ITERATION_MESSAGE,
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
