# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for the ``flocker-changestate`` command line tool.
"""
from os import getuid
from subprocess import check_output
from unittest import skipUnless

from twisted.python.procutils import which
from twisted.trial.unittest import TestCase
from twisted.python.filepath import FilePath
from twisted.internet import reactor

from ...volume.service import VolumeService, DEFAULT_CONFIG_PATH
from ...volume.filesystems.zfs import StoragePool
from ..script import ChangeStateScript
from ... import __version__


_require_installed = skipUnless(which("flocker-changestate"),
                                "flocker-changestate not installed")
_require_root = skipUnless(getuid() == 0,
                           "Root required to run these tests.")
from ..testtools import if_gear_configured


class FlockerChangeStateTests(TestCase):
    """Tests for ``flocker-changestate``."""

    @_require_installed
    # We really shouldn't need root, except there's a bug in this code
    # such that it overwrites /etc/flocker/volume.json - see
    # https://github.com/ClusterHQ/flocker/issues/301
    @_require_root
    def setUp(self):
        pass

    def test_version(self):
        """
        ``flocker-changestate`` is a command available on the system path
        """
        result = check_output([b"flocker-changestate"] + [b"--version"])
        self.assertEqual(result, b"%s\n" % (__version__,))


class ChangeStateScriptTests(TestCase):
    """
    Tests for ``ChangeStateScript``.

    XXX these tests overwrite the global volume manager config file:
    https://github.com/ClusterHQ/flocker/issues/301
    """
    @_require_root
    def setUp(self):
        pass

    def test_volume_service(self):
        """
        ``ChangeStateScript._deployer`` is created by default with a
        ``VolumeService``.
        """
        self.assertIsInstance(ChangeStateScript()._deployer.volume_service,
                              VolumeService)

    def test_volume_service_config_path(self):
        """
        ``ChangeStateScript._deployer`` is created by default with a
        ``VolumeService`` with the default config path.
        """
        self.assertEqual(
            ChangeStateScript()._deployer.volume_service._config_path,
            DEFAULT_CONFIG_PATH)

    def test_volume_service_pool(self):
        """
        ``ChangeStateScript._deployer`` is created by default with a
        ``VolumeService`` whose pool is the default ZFS pool.
        """
        self.assertEqual(
            ChangeStateScript()._deployer.volume_service.pool,
            StoragePool(reactor, b"flocker", FilePath(b"/flocker")))

    @if_gear_configured
    def test_deployer_gear_client(self):
        """
        ``ChangeState._deployer`` is configured with a gear client that works.
        """
        # Trial will fail the test if the returned Deferred fires with an
        # exception:
        return ChangeStateScript()._deployer.gear_client.list()


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
    # We really shouldn't need root, except there's a bug in this code
    # such that it overwrites /etc/flocker/volume.json - see
    # https://github.com/ClusterHQ/flocker/issues/301
    @_require_root
    def setUp(self):
        pass

    def test_version(self):
        """
        ``flocker-reportstate`` is a command available on the system path
        """
        result = check_output([b"flocker-reportstate"] + [b"--version"])
        self.assertEqual(result, b"%s\n" % (__version__,))
