# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Unit tests for the implementation of ``flocker-deploy``.
"""

from yaml import safe_dump

from twisted.python.filepath import FilePath
from twisted.python.usage import UsageError
from twisted.trial.unittest import TestCase, SynchronousTestCase
from twisted.internet.defer import Deferred

from ...testtools import (
    FlockerScriptTestsMixin, StandardOptionsTestsMixin, MemoryCoreReactor)
from ..script import DeployScript, DeployOptions
from ...control.httpapi import REST_API_PORT


class FlockerDeployTests(FlockerScriptTestsMixin, TestCase):
    """Tests for ``flocker-deploy``."""
    script = DeployScript
    options = DeployOptions
    command_name = u'flocker-deploy'


CONTROL_HOST = u"192.168.1.1"


class DeployOptionsTests(StandardOptionsTestsMixin, SynchronousTestCase):
    """Tests for :class:`DeployOptions`."""
    options = DeployOptions

    def default_port(self):
        """
        The default port to connect to is the REST API port.
        """
        options = self.options()
        deploy = FilePath(self.mktemp())
        app = FilePath(self.mktemp())

        deploy.setContent(b"{}")
        app.setContent(b"{}")

        self.assertEqual(options.parseOptions(
            [CONTROL_HOST, deploy.path, app.path])["port"], REST_API_PORT)

    def test_deploy_must_exist(self):
        """
        A ``UsageError`` is raised if the ``deployment_config`` file does not
        exist.
        """
        options = self.options()
        app = self.mktemp()
        FilePath(app).touch()
        deploy = b"/path/to/non-existent-file.cfg"
        exception = self.assertRaises(UsageError, options.parseOptions,
                                      [CONTROL_HOST, deploy, app])
        self.assertEqual('No file exists at {deploy}'.format(deploy=deploy),
                         str(exception))

    def test_app_must_exist(self):
        """
        A ``UsageError`` is raised if the ``app_config`` file does not
        exist.
        """
        options = self.options()
        deploy = self.mktemp()
        FilePath(deploy).touch()
        app = b"/path/to/non-existent-file.cfg"
        exception = self.assertRaises(UsageError, options.parseOptions,
                                      [CONTROL_HOST, deploy, app])
        self.assertEqual('No file exists at {app}'.format(app=app),
                         str(exception))

    def test_deployment_config_must_be_yaml(self):
        """
        A ``UsageError`` is raised if the supplied deployment
        configuration cannot be parsed as YAML.
        """
        options = self.options()
        deploy = FilePath(self.mktemp())
        app = FilePath(self.mktemp())

        deploy.setContent(b"{'foo':'bar', 'x':y, '':'")
        app.setContent(b"{}")

        e = self.assertRaises(
            UsageError, options.parseOptions,
            [CONTROL_HOST, deploy.path, app.path])

        expected = (
            "Deployment configuration at {path} could not be parsed "
            "as YAML"
        ).format(path=deploy.path)
        self.assertTrue(str(e).startswith(expected))

    def test_application_config_must_be_yaml(self):
        """
        A ``UsageError`` is raised if the supplied application
        configuration cannot be parsed as YAML.
        """
        options = self.options()
        deploy = FilePath(self.mktemp())
        app = FilePath(self.mktemp())

        deploy.setContent(b"{}")
        app.setContent(b"{'foo':'bar', 'x':y, '':'")

        e = self.assertRaises(
            UsageError, options.parseOptions,
            [CONTROL_HOST, deploy.path, app.path])

        expected = (
            "Application configuration at {path} could not be parsed "
            "as YAML"
        ).format(path=app.path)
        self.assertTrue(str(e).startswith(expected))


class FlockerDeployMainTests(TestCase):
    """
    Tests for ``DeployScript.main``.
    """
    def test_deferred_result(self):
        """
        ``DeployScript.main`` returns a ``Deferred`` on success.
        """
        temp = FilePath(self.mktemp())
        temp.makedirs()

        application_config_path = temp.child(b"app.yml")
        application_config_path.setContent(safe_dump({
            u"version": 1,
            u"applications": {},
        }))

        deployment_config_path = temp.child(b"deploy.yml")
        deployment_config_path.setContent(safe_dump({
            u"version": 1,
            u"nodes": {},
        }))

        options = DeployOptions()
        options.parseOptions([
            CONTROL_HOST, deployment_config_path.path,
            application_config_path.path])

        script = DeployScript()
        dummy_reactor = MemoryCoreReactor()
        self.assertIsInstance(script.main(dummy_reactor, options), Deferred)
