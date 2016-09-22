# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
Tests for ``flocker.common.runner``.
"""
from subprocess import CalledProcessError
import sys

from twisted.python.filepath import FilePath

from flocker.testtools import TestCase, random_name

from ..process import run_process, _ProcessResult


class RunProcessTests(TestCase):
    def test_success(self):
        """
        ``run_process`` returns a `__ProcessResult`` object with the status,
        command and combined stdout and stderr if the exit status is 0.
        """
        expected_returncode = 0
        expected_stdout = random_name(self).encode("utf8")
        expected_stderr = random_name(self).encode("utf8")
        sample_script = FilePath(__file__).sibling('sample_script.py')
        command = [
            sys.executable,
            sample_script.path,
            "--returncode", bytes(expected_returncode),
            "--stdout", expected_stdout,
            "--stderr", expected_stderr,
        ]
        result = run_process(command)
        self.assertEqual(
            _ProcessResult(
                command=command,
                status=expected_returncode,
                output=expected_stdout + expected_stderr,
            ),
            result
        )

    def test_error(self):
        """
        ``run_process`` raises CalledProcessError when status !=0.
        The string representation of the raised error includes the combined
        stdout and stderr.
        """
        expected_returncode = 1
        expected_stdout = random_name(self).encode("utf8")
        expected_stderr = random_name(self).encode("utf8")
        sample_script = FilePath(__file__).sibling('sample_script.py')
        command = [
            sys.executable,
            sample_script.path,
            "--returncode", bytes(expected_returncode),
            "--stdout", expected_stdout,
            "--stderr", expected_stderr,
        ]

        e = self.assertRaises(CalledProcessError, run_process, command)

        self.assertEqual(
            (command, expected_returncode, expected_stdout + expected_stderr),
            (e.cmd, e.returncode, e.output)
        )
        self.assertIn(expected_stdout + expected_stderr, unicode(e))

    def test_signal(self):
        """
        ``run_process`` raises CalledProcessError when it exits due to a signal
        and the signal is included in the exception.
        """
        expected_returncode = -1
        expected_stdout = random_name(self).encode("utf8")
        expected_stderr = random_name(self).encode("utf8")
        sample_script = FilePath(__file__).sibling('sample_script.py')
        command = [
            sys.executable,
            sample_script.path,
            "--returncode", bytes(expected_returncode),
            "--stdout", expected_stdout,
            "--stderr", expected_stderr,
        ]

        e = self.assertRaises(CalledProcessError, run_process, command)

        self.assertEqual(
            (command, expected_returncode, expected_stdout + expected_stderr),
            (e.cmd, e.returncode, e.output)
        )
        self.assertIn(expected_stdout + expected_stderr, unicode(e))
