# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
Tests for ``flocker.common.process``.
"""
from subprocess import CalledProcessError
import sys

from pyrsistent import PClass, field
from twisted.python.filepath import FilePath

from ...testtools import TestCase, random_name
from ..process import run_process, _ProcessResult

SAMPLE_SCRIPT_FILE = FilePath(__file__).sibling('sample_script.py')


class SampleScript(PClass):
    """
    The parameters which will be supplied when calling ``SAMPLE_SCRIPT_FILE``
    in tests.
    """
    returncode = field(type=int)
    stdout = field(type=bytes)
    stderr = field(type=bytes)

    def commandline(self):
        """
        :returns: A ``list`` suitable for passing to ``run_process`` in tests.
        """
        return [
            sys.executable,
            SAMPLE_SCRIPT_FILE.path,
            "--returncode", bytes(self.returncode),
            "--stdout", self.stdout,
            "--stderr", self.stderr,
        ]


class RunProcessTests(TestCase):
    """
    Tests for ``run_process``.
    """
    def command_for_test(self, returncode):
        """
        Construct a ``SampleScript`` which generates a command line for
        ``SAMPLE_SCRIPT_FILE`` with test case specific stdout and stderr and
        the supplied ``returncode``.
        """
        return SampleScript(
            returncode=returncode,
            stdout=random_name(self).encode("utf8"),
            stderr=random_name(self).encode("utf8"),
        )

    def test_success(self):
        """
        ``run_process`` returns a `__ProcessResult`` object with the status,
        command and combined stdout and stderr if the exit status is 0.
        """
        command = self.command_for_test(returncode=0)
        result = run_process(command.commandline())
        self.assertEqual(
            _ProcessResult(
                command=command.commandline(),
                status=command.returncode,
                output=command.stdout + command.stderr,
            ),
            result
        )

    def check_run_process_error(self, expected_returncode):
        """
        Run ``SAMPLE_SCRIPT_FILE`` with ``run_process`` and assert that
        ``CalledProcessError`` is raised.
        """
        command = self.command_for_test(returncode=expected_returncode)
        e = self.assertRaises(
            CalledProcessError,
            run_process,
            command.commandline()
        )
        self.assertEqual(
            (command.commandline(),
             command.returncode,
             command.stdout + command.stderr),
            (e.cmd, e.returncode, e.output)
        )
        self.assertIn(command.stdout + command.stderr, unicode(e))

    def test_error(self):
        """
        ``run_process`` raises CalledProcessError when status !=0.
        The string representation of the raised error includes the combined
        stdout and stderr.
        """
        self.check_run_process_error(expected_returncode=1)

    def test_error_signal(self):
        """
        ``run_process`` raises CalledProcessError when it exits due to a signal
        and the signal is included in the exception.
        """
        self.check_run_process_error(expected_returncode=-1)
