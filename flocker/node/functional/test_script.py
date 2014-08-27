# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for the ``flocker-changestate`` command line tool.
"""

from os import getuid
from subprocess import check_output
from unittest import skipUnless

from twisted.python.procutils import which
from twisted.trial.unittest import TestCase

from ... import __version__


_require_installed = skipUnless(which("flocker-changestate"),
                                "flocker-changestate not installed")
_require_root = skipUnless(getuid() == 0,
                           "Root required to run these tests.")


class FlockerChangeStateTests(TestCase):
    """Tests for ``flocker-changestate``."""

    @_require_installed
    def test_version(self):
        """
        ``flocker-changestate`` is a command available on the system path
        """
        result = check_output([b"flocker-changestate"] + [b"--version"])
        self.assertEqual(result, b"%s\n" % (__version__,))


class ReportStateScriptTests(TestCase):
    """
    Tests for ``ReportStateScript``.
    """

    @_require_root
    def setUp(self):
        pass


class FlockerReportStateTests(TestCase):
    """Tests for ``flocker-reportstate``."""

    @_require_installed
    def test_version(self):
        """
        ``flocker-reportstate`` is a command available on the system path
        """
        result = check_output([b"flocker-reportstate"] + [b"--version"])
        self.assertEqual(result, b"%s\n" % (__version__,))
