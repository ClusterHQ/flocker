# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Unit tests for the implementation ``flocker-deploy``.
"""
from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase, SynchronousTestCase

from ...testtools import FlockerScriptTestsMixin, StandardOptionsTestsMixin
from ..script import DeployScript, DeployOptions


class FlockerDeployTests(FlockerScriptTestsMixin, TestCase):
    """Tests for ``flocker-deploy``."""
    script = DeployScript
    options = DeployOptions
    command_name = u'flocker-deploy'


class DeployOptionsTests(StandardOptionsTestsMixin, SynchronousTestCase):
    """Tests for :class:`DeployOptions`."""
    options = DeployOptions

    def test_custom_configs(self):
        """Custom config files can be specified."""
        options = self.options()
        deploy = self.mktemp()
        app = self.mktemp()
        options.parseOptions([deploy, app])
        self.assertEqual(options,
            {'deploy': deploy, 'app': app, 'verbosity': 0})

    def test_deploy_must_exist(self):
        """The ``deploy`` config file must be a real file."""
        options = self.options()
        app = self.mktemp()
        options.parseOptions([b"/path/nonexistantfile.json", app])
        self.assertEqual(options,
            {'deploy': b"/path/nonexistantfile.json", 'app': app, 'verbosity': 0})

    def test_app_must_exist(self):
        """The ``app`` config file must be a real file."""
        options = self.options()
        deploy = self.mktemp()
        options.parseOptions([deploy, b"/path/nonexistantfile.json"])
        self.assertEqual(options,
            {'deploy': deploy, 'app': b"/path/nonexistantfile.json", 'verbosity': 0})


class FlockerDeployMainTests(SynchronousTestCase):
    """
    Tests for ``DeployScript.main``.
    """
    def test_deferred_result(self):
        """
        ``DeployScript.main`` returns a ``Deferred`` on success.
        """
        script = DeployScript()
        dummy_reactor = object()
        options = {}
        self.assertIs(
            None,
            self.successResultOf(script.main(dummy_reactor, options))
        )