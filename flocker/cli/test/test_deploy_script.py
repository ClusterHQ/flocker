# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Unit tests for the implementation ``flocker-deploy``.
"""

from twisted.trial.unittest import TestCase, SynchronousTestCase

from ...testtools import FlockerScriptTestsMixin, StandardOptionsTestsMixin
from ..script import DeployScript, DeployOptions


class FlockerDeployTests(FlockerScriptTestsMixin, TestCase):
    """Tests for ``flocker-deploy``."""
    script = DeployScript
    options = DeployOptions
    command_name = u'flocker-deploy'


class DeployOptionsTests(StandardOptionsTestsMixin, SynchronousTestCase):
    """Tests for :class:`FlockerVolumeOptions`."""
    options = DeployOptions

    # def test_default_config(self):
    #     """By default the config file is ``b'/etc/flocker/volume.json'``."""
    #     options = self.options()
    #     options.parseOptions([])
    #     self.assertEqual(options["config"],
    #                      FilePath(b"/etc/flocker/volume.json"))
    #
    # def test_custom_config(self):
    #     """A custom config file can be specified with ``--config``."""
    #     options = self.options()
    #     options.parseOptions([b"--config", b"/path/somefile.json"])
    #     self.assertEqual(options["config"],
    #                      FilePath(b"/path/somefile.json"))
