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
        """Custom config files can be specified, and stored as
        ``FilePath``s."""
        options = self.options()
        deploy = self.mktemp()
        FilePath(deploy).touch()
        app = self.mktemp()
        FilePath(app).touch()
        options.parseOptions([deploy, app])
        self.assertEqual(options,
                         {'deploy': FilePath(deploy),
                          'app': FilePath(app),
                          'verbosity': 0})

    def test_deploy_must_exist(self):
        """The ``deploy`` config file must be a real file."""
        options = self.options()
        self.assertRaises(ValueError, options.parseOptions,
                          [b"/path/to/nonexistantfile.json", self.mktemp()])

    def test_app_must_exist(self):
        """The ``app`` config file must be a real file."""
        options = self.options()
        self.assertRaises(ValueError, options.parseOptions,
                          [self.mktemp(), b"/path/to/nonexistantfile.json"])

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
