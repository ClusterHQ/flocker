"""Tests for :module:`flocker.volume.script`."""

from twisted.trial.unittest import TestCase
from twisted.python.filepath import FilePath

from ..script import FlockerVolumeOptions


class OptionsTestCase(TestCase):
    """Tests for :class:`FlockerVolumeOptions`."""

    def test_defaultConfig(self):
        """By default the config file is ``b'/etc/flocker/volume.json'``."""
        options = FlockerVolumeOptions()
        options.parseOptions([])
        self.assertEqual(options["config"],
                         FilePath(b"/etc/flocker/volume.json"))

    def test_customConfig(self):
        """A custom config file can be specified with ``--config``."""
        options = FlockerVolumeOptions()
        options.parseOptions([b"--config", b"/path/somefile.json"])
        self.assertEqual(options["config"],
                         FilePath(b"/path/somefile.json"))
