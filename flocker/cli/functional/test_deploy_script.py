# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Functional tests for the ``flocker-deploy`` command line tool."""
from subprocess import check_output
from unittest import skipUnless

from twisted.python.procutils import which
from twisted.trial.unittest import TestCase

from ... import __version__


_require_installed = skipUnless(which("flocker-deploy"),
                                "flocker-deploy not installed")


class FlockerDeployTests(TestCase):
    """Tests for ``flocker-deploy``."""

    @_require_installed
    def setUp(self):
        pass

    def test_version(self):
        """``flocker-deploy --version`` returns the current version."""
        result = check_output([b"flocker-deploy"] + [b"--version"])
        self.assertEqual(result, b"%s\n" % (__version__,))
