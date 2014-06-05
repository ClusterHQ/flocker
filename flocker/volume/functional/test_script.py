# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Functional tests for the ``flocker-volume`` command line tool."""

from subprocess import check_output
import json
import os

from twisted.trial.unittest import TestCase
from twisted.python.filepath import FilePath

from ... import __version__


def run(*args):
    """Run ``flocker-volume`` with the given arguments.

    :param args: Additional command line arguments as ``bytes``.

    :return: The output of standard out.
    :raises: If exit code is not 0.
    """
    return check_output([b"flocker-volume"] + list(args))


class FlockerVolumeTests(TestCase):
    """Tests for ``flocker-volume``."""

    if not os.getenv("FLOCKER_INSTALLED"):
        skip = "flocker-volume not installed"

    def test_version(self):
        """``flocker-volume --version`` returns the current version."""
        result = run(b"--version")
        self.assertEqual(result, b"%s\n" % (__version__,))

    def test_config(self):
        """``flocker-volume --config path`` writes a JSON file at that path."""
        path = FilePath(self.mktemp())
        run(b"--config", path.path)
        self.assertTrue(json.loads(path.getContent()))
