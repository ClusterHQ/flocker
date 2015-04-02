# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.testtools``.
"""

from subprocess import CalledProcessError

from twisted.trial.unittest import SynchronousTestCase

from flocker.testtools import run_process


class RunProcessTests(SynchronousTestCase):
    """
    Tests for ``run_process``.
    """
    def test_on_error(self):
        """
        If the child process exits with a non-zero exit status, ``run_process``
        raises ``CalledProcessError`` initialized with the command, exit
        status, and any output.
        """
        command = [b"/bin/sh", b"-c", "echo goodbye && exec false"]
        exception = self.assertRaises(
            CalledProcessError,
            run_process,
            command,
        )
        expected = (1, command, b"goodbye\n")
        actual = (
            exception.returncode, exception.cmd, exception.output
        )
        self.assertEqual(expected, actual)
