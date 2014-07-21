# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for :module:`flocker.node.script`.
"""

from twisted.trial.unittest import SynchronousTestCase
from twisted.python.usage import UsageError
from yaml import safe_dump
from ...testtools import FlockerScriptTestsMixin, StandardOptionsTestsMixin
from ..script import (
    ChangeStateOptions, ChangeStateScript,
    ReportStateScript, ReportStateOptions)
from .._deploy import Deployer
from .._model import Application, Deployment, DockerImage, Node


class ChangeStateScriptTests(FlockerScriptTestsMixin, SynchronousTestCase):
    """
    Tests for ``ChangeStateScript``.
    """
    script = staticmethod(lambda: ChangeStateScript(lambda: None))
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
        script = ChangeStateScript(lambda: None)
        self.assertIsInstance(script._deployer, Deployer)

    def test_deployer_volume_service(self):
        """
        ``ChangeStateScript._deployer`` is configured with a volume service
        created by the given callable.
        """
        service = object()
        script = ChangeStateScript(lambda: service)
        self.assertIs(script._deployer._volume_service, service)

    def test_main_calls_deployer_change_node_state(self):
        """
        ``ChangeStateScript.main`` calls ``Deployer.change_node_state`` with
        the ``Deployment`` and `hostname` supplied on the command line.
        """
        script = ChangeStateScript(lambda: None)

        change_node_state_calls = []

        def spy_change_node_state(desired_state, hostname):
            """
            A stand in for ``Deployer.change_node_state`` which records calls
            made to it.
            """
            change_node_state_calls.append((desired_state, hostname))

        self.patch(
            script._deployer, 'change_node_state', spy_change_node_state)

        expected_deployment = Deployment(nodes=frozenset())
        expected_hostname = b'node1.example.com'
        options = dict(deployment=expected_deployment,
                       hostname=expected_hostname)
        script.main(reactor=object(), options=options)

        self.assertEqual(
            [(expected_deployment, expected_hostname)],
            change_node_state_calls
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
            image=DockerImage(repository=u'hybridlogic/mysql5.9',
                              tag=u'latest'))

        node = Node(hostname='node1.example.com',
                    applications=frozenset([application]))
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
            [safe_dump(deployment_config),
             safe_dump(application_config),
             b'node1.example.com'])

        self.assertEqual(
            Deployment(nodes=frozenset([node])), options['deployment'])

    def test_configuration_error(self):
        """
        If the supplied configuration strings are valid `YAML` but are not
        valid, a ``UsageError`` is raised with a string representation of the
        error.
        """
        options = self.options()
        application = Application(
            name=u'mysql-hybridcluster',
            image=DockerImage(
                repository=u'hybridlogic/mysql5.9', tag=u'latest'),
        )

        node = Node(hostname='node1.example.com',
                    applications=frozenset([application]))
        options = self.options()
        deployment_config = {"nodes": {node.hostname: [application.name]},
                             "version": 1}

        exception = self.assertRaises(
            UsageError,
            options.parseOptions,
            [safe_dump(deployment_config), safe_dump({}), b'node1.example.com']
        )

        self.assertEqual(
            str(exception),
            ("Configuration Error: "
             "Application configuration has an error. Missing "
             "'applications' key.")
        )

    def test_invalid_deployment_yaml(self):
        """
        If the supplied deployment_config is not valid `YAML`, a ``UsageError``
        is raised.
        """
        options = self.options()
        deployment_bad_yaml = "{'foo':'bar', 'x':y, '':'"
        e = self.assertRaises(
            UsageError, options.parseOptions,
            [deployment_bad_yaml, b'', b'node1.example.com'])

        # See https://github.com/ClusterHQ/flocker/issues/282 for more complete
        # testing of this string.
        self.assertTrue(
            str(e).startswith('Deployment config could not be parsed as YAML')
        )

    def test_invalid_application_yaml(self):
        """
        If the supplied application_config is not valid `YAML`, a
        ``UsageError`` is raised.
        """
        options = self.options()
        application_bad_yaml = "{'foo':'bar', 'x':y, '':'"
        e = self.assertRaises(
            UsageError, options.parseOptions,
            [b'', application_bad_yaml, b'node1.example.com'])

        # See https://github.com/ClusterHQ/flocker/issues/282 for more complete
        # testing of this string.
        self.assertTrue(
            str(e).startswith('Application config could not be parsed as YAML')
        )

    def test_hostname_key(self):
        """
        The supplied hostname is assigned to a `hostname` key.
        """
        expected_hostname = u'foobar.example.com'
        options = self.options()
        options.parseOptions(
            [b'{nodes: {}, version: 1}',
             b'{applications: {}, version: 1}',
             expected_hostname.encode('ascii')])
        self.assertEqual(
            (expected_hostname, unicode),
            (options['hostname'], type(options['hostname']))
        )

    def test_nonascii_hostname(self):
        """
        A ``UsageError`` is raised if the supplied hostname is not ASCII
        encoded.
        """
        hostname = u'\xa3'.encode('utf8')
        options = self.options()
        e = self.assertRaises(
            UsageError,
            options.parseOptions,
            [b'{nodes: {}, version: 1}',
             b'{applications: {}, version: 1}',
             hostname]
        )

        self.assertEqual(
            "Non-ASCII hostname: {hostname}".format(hostname=hostname),
            str(e)
        )


class ReportStateOptionsTests(StandardOptionsTestsMixin, SynchronousTestCase):
    """
    Tests for :class:`ReportStateOptions`.
    """
    options = ReportStateOptions

    def test_no_options(self):
        """
        ``ReportStateOptions`` does not take any (non-standard) options.
        """
        options = self.options()
        options.parseOptions([])

    def test_wrong_number_options(self):
        """
        If any additional arguments are supplied, a ``UsageError`` is raised.
        """
        options = self.options()
        e = self.assertRaises(
            UsageError,
            options.parseOptions,
            ['someparameter']
        )
        self.assertEqual(str(e), b"Wrong number of arguments.")


class ReportStateScriptTests(FlockerScriptTestsMixin, SynchronousTestCase):
    """
    Tests for ``ReportStateScript``.
    """
    script = staticmethod(lambda: ReportStateScript(lambda: None))
    options = ReportStateOptions
    command_name = u'flocker-reportstate'


class ReportStateScriptMainTests(SynchronousTestCase):
    """
    Tests for ``ReportStateScript.main``.
    """
    def test_deployer_type(self):
        """
        ``ReportStateScript._deployer`` is an instance of :class:`Deployer`.
        """
        script = ReportStateScript(lambda: None)
        self.assertIsInstance(script._deployer, Deployer)

    def test_yaml_callback(self):
        """
        ``ReportStateScript.main`` returns a deferred which fires with the YAML
        representation of the applications from
        ``Deployer.discover_node_configuration``
        """
        script = ReportStateScript()
        script.main(reactor=object(), options=[])
