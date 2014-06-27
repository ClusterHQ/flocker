# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Functional tests for the ``flocker-deploy`` command line tool."""
from subprocess import check_output
import os

from twisted.trial.unittest import TestCase

from ... import __version__


class FlockerDeployTests(TestCase):
    """Tests for ``flocker-deploy``."""

    if not os.getenv("FLOCKER_INSTALLED"):
        skip = ("flocker-deploy not installed or FLOCKER_INSTALLED "
                "environment variable is not set.")

    def test_version(self):
        """``flocker-deploy --version`` returns the current version."""
        result = check_output([b"flocker-deploy"] + [b"--version"])
        self.assertEqual(result, b"%s\n" % (__version__,))
