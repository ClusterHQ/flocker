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
from ...testtools import skip_on_broken_permissions

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

    def change_uid(test_method):
        """
        Skips the wrapped test when the temporary directory is on a
        filesystem with broken permissions.

        Virtualbox's shared folder (as used for :file:`/vagrant`) doesn't entirely
        respect changing permissions. For example, this test detects running on a
        shared folder by the fact that all permissions can't be removed from a
        file.

        :param callable test_method: Test method to wrap.
        :return: The wrapped method.
        :raise SkipTest: when the temporary directory is on a filesystem with
            broken permissions.
        """
        @wraps(test_method)
        def wrapper(case, *args, **kwargs):
            from twisted.python.util import switchUID
            if os.getuid() == 0:
                pass
                # os.setuid(65534)
                # os.setuid(65534)
                # a
            # test_method.addCleanup(os.seteuid(0))
            # test_method.addCleanup(os.setuid(0))
            return test_method(case, *args, **kwargs)
        return wrapper

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

    # @skipIf(os.getuid() == 0, "root doesn't get permission errors.")
    # @change_uid
    # @skip_on_broken_permissions
    def test_no_permission(self):
        """If the config file is not writeable a meaningful response is
        written.
        """
        # import pdb; pdb.set_trace()
        if os.getuid() == 0:
            os.seteuid(1)
            self.addCleanup(os.seteuid, 0)
            # os.setuid(1)
            # self.addCleanup(os.setuid, 0)
        path = FilePath(self.mktemp())
        path.makedirs()
        path.chmod(0)
        self.addCleanup(path.chmod, 0o777)
        config = path.child(b"out.json")
        if os.getuid() == 0:
            os.seteuid(1)
            self.addCleanup(os.seteuid, 0)
        result = run_expecting_error(b"--config", config.path)
        self.assertEqual(result,
                         b"Writing config file %s failed: Permission denied\n"
                         % (config.path,))
