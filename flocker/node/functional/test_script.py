# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for the ``flocker-changestate`` command line tool.
"""
from subprocess import check_output
from unittest import skipUnless

from twisted.python.procutils import which
from twisted.trial.unittest import TestCase

from ... import __version__


_require_installed = skipUnless(which("flocker-changestate"),
                                "flocker-changestate not installed")


class FlockerDeployTests(TestCase):
    """Tests for ``flocker-changestate``."""

    @_require_installed
    def setUp(self):
        pass

    def test_version(self):
        """
        ``flocker-changestate`` is a command available on the system path
        """
        result = check_output([b"flocker-changestate"] + [b"--version"])
        self.assertEqual(result, b"%s\n" % (__version__,))

