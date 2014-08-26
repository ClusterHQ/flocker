# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for :module:`flocker.volume.script`.
"""

from twisted.trial.unittest import SynchronousTestCase
from twisted.python.filepath import FilePath
from twisted.application.service import Service

from ...testtools import StandardOptionsTestsMixin
from ..script import VolumeOptions, VolumeManagerScript


class VolumeManagerScriptMainTests(SynchronousTestCase):
    """
    Tests for ``VolumeManagerScript.main``.
    """
    def test_deferred_result(self):
        """
        ``VolumeScript.main`` returns a ``Deferred`` on success.
        """
        script = VolumeManagerScript()
        options = VolumeOptions()
        options["config"] = FilePath(self.mktemp())
        dummy_reactor = object()
        result = script.main(dummy_reactor, options, Service())
        self.assertIs(None, self.successResultOf(result))


class VolumeOptionsTests(StandardOptionsTestsMixin, SynchronousTestCase):
    """Tests for :class:`FlockerVolumeOptions`."""
    options = VolumeOptions

    def test_default_config(self):
        """By default the config file is ``b'/etc/flocker/volume.json'``."""
        options = self.options()
        options.parseOptions([])
        self.assertEqual(options["config"],
                         FilePath(b"/etc/flocker/volume.json"))

    def test_custom_config(self):
        """A custom config file can be specified with ``--config``."""
        options = self.options()
        options.parseOptions([b"--config", b"/path/somefile.json"])
        self.assertEqual(options["config"],
                         FilePath(b"/path/somefile.json"))
