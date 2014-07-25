# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Functional tests for the ``flocker-volume`` command line tool."""

from functools import wraps
from subprocess import check_output, Popen, PIPE
import json
import os
from unittest import skipIf, skipUnless

from twisted.trial.unittest import TestCase, SkipTest
from twisted.python.filepath import FilePath
from twisted.python.procutils import which

from ... import __version__
from ...testtools import skip_on_broken_permissions, run_as_user

_require_installed = skipUnless(which("flocker-volume"),
                                "flocker-volume not installed")


def run(*args):
    """Run ``flocker-volume`` with the given arguments.

    :param args: Additional command line arguments as ``bytes``.

    :return: The output of standard out.
    :raises: If exit code is not 0.
    """
    return check_output([b"flocker-volume"] + list(args))


def run_expecting_error(*args):
    """Run ``flocker-volume`` with the given arguments.

    :param args: Additional command line arguments as ``bytes``.

    :return: The output of standard error.
    :raises: If exit code is 0.
    """
    process = Popen([b"flocker-volume"] + list(args), stderr=PIPE)
    result = process.stderr.read()
    exit_code = process.wait()
    if exit_code == 0:
        raise AssertionError("flocker-volume exited with code 0.")
    return result


class FlockerVolumeTests(TestCase):
    """Tests for ``flocker-volume``."""

    @_require_installed
    def setUp(self):
        pass

    def test_version(self):
        """``flocker-volume --version`` returns the current version."""
        result = run(b"--version")
        self.assertEqual(result, b"%s\n" % (__version__,))

    def test_config(self):
        """``flocker-volume --config path`` writes a JSON file at that path."""
        path = FilePath(self.mktemp())
        run(b"--config", path.path)
        self.assertTrue(json.loads(path.getContent()))

    @skip_on_broken_permissions
    @run_as_user("vagrant", "vagrant")
    def test_no_permission(self):
        """If the config file is not writeable a meaningful response is
        written.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        path.chmod(0)
        self.addCleanup(path.chmod, 0o777)
        config = path.child(b"out.json")
        result = run_expecting_error(b"--config", config.path)
        self.assertEqual(result,
                         b"Writing config file %s failed: Permission denied\n"
                         % (config.path,))
