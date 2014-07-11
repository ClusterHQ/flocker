# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for :module:`flocker.node.script`.
"""

from twisted.trial.unittest import SynchronousTestCase
from twisted.python.usage import UsageError
from yaml import safe_dump
from ...testtools import FlockerScriptTestsMixin, StandardOptionsTestsMixin
from ..script import ChangeStateOptions, ChangeStateScript
from .._deploy import Deployer
from .._model import Application, Deployment, DockerImage, Node


class ChangeStateScriptTests(FlockerScriptTestsMixin, SynchronousTestCase):
    """
    Tests for L{ChangeStateScript}.
    """
    script = ChangeStateScript
    options = ChangeStateOptions
    command_name = u'flocker-changestate'


class ChangeStateScriptMainTests(SynchronousTestCase):
    """
    Tests for ``ChangeStateScript.main``.
    """

    def test_deployer_type(self):
        """
        ``ChangeStateScript._deployer`` is an instance of :class:`Deployer`.
        """
        script = ChangeStateScript()
        self.assertIsInstance(script._deployer, Deployer)

    def test_deferred_result(self):
        """
        ``ChangeStateScript.main`` returns a ``Deferred`` on success.
        """
        script = ChangeStateScript()
        options = ChangeStateOptions()
        dummy_reactor = object()
        self.assertIs(
            None,
            self.successResultOf(script.main(dummy_reactor, options))
        )


class ChangeStateOptionsTests(StandardOptionsTestsMixin, SynchronousTestCase):
    """
    Tests for :class:`ChangeStateOptions`.
    """
    options = ChangeStateOptions

    def test_custom_configs(self):
        """
        The supplied configuration strings are parsed as a :class:`Deployment`
        on the options instance.
        """
        application = Application(
            name=u'mysql-hybridcluster',
            image=DockerImage(
                repository=u'hybridlogic/mysql5.9', tag=u'latest'),
        )

        node = Node(hostname='node1.example.com', applications=frozenset([application]))
        options = self.options()
        deployment_config = {"nodes": {node.hostname: [application.name]},
                             "version": 1}

        application_config = dict(
            version=1,
            applications={
                application.name: {'image': 'hybridlogic/mysql5.9:latest'}
            }
        )

        options.parseOptions(
            [safe_dump(deployment_config), safe_dump(application_config)])

        self.assertDictContainsSubset(
            {'deployment': Deployment(nodes=frozenset([node]))},
            options
        )

    def test_invalid_deployment_configs(self):
        """
        If the supplied deployment_config is not valid `YAML`, a
        ``UsageError`` is raised.
        """
        options = self.options()
        deployment_bad_yaml = "{'foo':'bar', 'x':y, '':'"
        e = self.assertRaises(
            UsageError, options.parseOptions, [deployment_bad_yaml, b''])

        self.assertTrue(
            str(e).startswith('Deployment config could not be parsed as YAML')
        )

    def test_invalid_application_configs(self):
        """
        If the supplied application_config is not valid `YAML`, a
        ``UsageError`` is raised.
        """
        options = self.options()
        application_bad_yaml = "{'foo':'bar', 'x':y, '':'"
        e = self.assertRaises(
            UsageError, options.parseOptions, [b'', application_bad_yaml])

        self.assertTrue(
            str(e).startswith('Application config could not be parsed as YAML')
        )
