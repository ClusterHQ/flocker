# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Unit tests for the implementation ``flocker-deploy``.
"""
from twisted.python.filepath import FilePath
from twisted.python.usage import UsageError
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
        ``FilePath``\ s."""
        options = self.options()
        deploy = self.mktemp()
        FilePath(deploy).touch()
        app = self.mktemp()
        FilePath(app).touch()
        options.parseOptions([deploy, app])
        self.assertEqual(options,
                         {'deployment_config': FilePath(deploy),
                          'app_config': FilePath(app),
                          'verbosity': 0})

    def test_deploy_must_exist(self):
        """The ``deployment_config`` file must exist."""
        options = self.options()
        app = self.mktemp()
        FilePath(app).touch()
        deploy = b"/path/to/non-existent-file.cfg"
        self.assertRaisesRegexp(UsageError, 'No file exists at %s' % deploy,
                                options.parseOptions, [deploy, app])

    def test_app_must_exist(self):
        """The ``app_config`` file must exist."""
        options = self.options()
        deploy = self.mktemp()
        FilePath(deploy).touch()
        app = b"/path/to/non-existent-file.cfg"
        self.assertRaisesRegexp(UsageError, 'No file exists at %s' % app,
                                options.parseOptions, [deploy, app])


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
