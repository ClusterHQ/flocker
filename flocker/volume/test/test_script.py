# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Tests for :module:`flocker.volume.script`."""

import io, sys

from twisted.trial.unittest import SynchronousTestCase
from twisted.python.filepath import FilePath

from ..script import FlockerVolumeOptions

from ... import __version__


class StandardOptionsTestsMixin(object):
    """
    Tests for the standard options that should be available on every flocker
    command.
    """
    options = None

    def assert_version_option(self, argument):
        """
        Flocker commands have a I{--version} option which prints the current
        version string to stdout and causes the command to exit with status 0.
        """
        output = io.BytesIO()
        # XXX: Is there a better way to capture stdout in trial? I think there
        # is.
        self.patch(sys, 'stdout', output)
        error = self.assertRaises(
            SystemExit, self.options().parseOptions, [argument])
        self.assertEqual(
            (__version__ + '\n', 0), (output.getvalue(), error.code))


    def test_version_long(self):
        """
        Flocker commands have a I{--version} option which prints the current
        version string to stdout and causes the command to exit with status 0.
        """
        self.assert_version_option('--version')


    def test_version_short(self):
        """
        Flocker commands have a I{-v} option which prints the current
        version string to stdout and causes the command to exit with status 0.
        """
        self.assert_version_option('-v')



class FlockerVolumeOptionsTests(StandardOptionsTestsMixin, SynchronousTestCase):
    """
    Tests for L{FlockerVolumeOptions}.
    """
    options = FlockerVolumeOptions



class OptionsTestCase(SynchronousTestCase):
    """Tests for :class:`FlockerVolumeOptions`."""

    def test_default_config(self):
        """By default the config file is ``b'/etc/flocker/volume.json'``."""
        options = FlockerVolumeOptions()
        options.parseOptions([])
        self.assertEqual(options["config"],
                         FilePath(b"/etc/flocker/volume.json"))

    def test_custom_config(self):
        """A custom config file can be specified with ``--config``."""
        options = FlockerVolumeOptions()
        options.parseOptions([b"--config", b"/path/somefile.json"])
        self.assertEqual(options["config"],
                         FilePath(b"/path/somefile.json"))
