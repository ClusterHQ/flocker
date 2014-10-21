# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for the ``flocker-changestate`` command line tool.
"""

from subprocess import check_output
from unittest import skipUnless

from twisted.python.procutils import which
from twisted.trial.unittest import TestCase

from ... import __version__


def make_script_tests(executable):
    """
    Generate a test suite which applies to any Flocker-installed node script.

    :param bytes executable: The basename of the script to be tested.

    :return: A ``TestCase`` subclass which defines some tests applied to the
        given executable.
    """
    class ScriptTests(TestCase):
        @skipUnless(which(executable), executable + " not installed")
        def test_version(self):
            """
            The script is a command available on the system path.
            """
            result = check_output([executable] + [b"--version"])
            self.assertEqual(result, b"%s\n" % (__version__,))
    return ScriptTests


class FlockerChangeStateTests(make_script_tests(b"flocker-changestate")):
    """
    Tests for ``flocker-changestate``.
    """


class FlockerReportStateTests(make_script_tests(b"flocker-reportstate")):
    """
    Tests for ``flocker-reportstate``.
    """
