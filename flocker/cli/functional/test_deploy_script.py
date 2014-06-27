# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Functional tests for the ``flocker-deploy`` command line tool."""
from subprocess import check_output, Popen, PIPE
import os

from twisted.trial.unittest import TestCase

from ... import __version__


# TODO This is basically from flocker-volume's tests, should be split out
def run(*args):
    """Run ``flocker-deploy`` with the given arguments.

    :param args: Additional command line arguments as ``bytes``.

    :return: The output of standard out.
    :raises: If exit code is not 0.
    """
    return check_output([b"flocker-deploy"] + list(args))


def run_expecting_error(*args):
    """Run ``flocker-deploy`` with the given arguments.

    :param args: Additional command line arguments as ``bytes``.

    :return: The output of standard error.
    :raises: If exit code is 0.
    """
    process = Popen([b"flocker-deploy"] + list(args), stderr=PIPE)
    result = process.stderr.read()
    exit_code = process.wait()
    if exit_code == 0:
        raise AssertionError("flocker-deploy exited with code 0.")
    return result


class FlockerDeployTests(TestCase):
    """Tests for ``flocker-deploy``."""

    if not os.getenv("FLOCKER_INSTALLED"):
        skip = ("flocker-deploy not installed or FLOCKER_INSTALLED "
                "environment variable is not set.")

    def test_version(self):
        """``flocker-deploy --version`` returns the current version."""
        result = run(b"--version")
        self.assertEqual(result, b"%s\n" % (__version__,))
