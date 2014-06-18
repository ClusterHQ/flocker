# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Tests for :module:`flocker.volume.script`."""

from twisted.trial.unittest import SynchronousTestCase
from twisted.python.filepath import FilePath

from flocker.common.test.test_script import (
    FlockerScriptTestsMixin, StandardOptionsTestsMixin)
from flocker.volume.script import VolumeOptions, VolumeScript


class VolumeScriptTests(FlockerScriptTestsMixin, SynchronousTestCase):
    """
    Tests for L{VolumeScript}.
    """
    script = VolumeScript
    options = VolumeOptions
    command_name = 'flocker-volume'



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
