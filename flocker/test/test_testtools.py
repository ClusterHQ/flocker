# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.testtools``.
"""

from subprocess import CalledProcessError

from flocker.testtools import run_process, TestCase


class RunProcessTests(TestCase):
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
