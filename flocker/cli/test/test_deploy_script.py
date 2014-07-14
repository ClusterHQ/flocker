# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Unit tests for the implementation ``flocker-deploy``.
"""

from yaml import safe_dump
from threading import current_thread

from twisted.python.filepath import FilePath
from twisted.python.usage import UsageError
from twisted.trial.unittest import TestCase, SynchronousTestCase
from twisted.internet.defer import succeed
from twisted.internet import reactor

from ...testtools import FlockerScriptTestsMixin, StandardOptionsTestsMixin
from ..script import DeployScript, DeployOptions
from .._sshconfig import DEFAULT_SSH_DIRECTORY
from ...node import Application, Deployment, DockerImage, Node
from ...volume._ipc import ProcessNode, FakeNode


class FlockerDeployTests(FlockerScriptTestsMixin, TestCase):
    """Tests for ``flocker-deploy``."""
    script = DeployScript
    options = DeployOptions
    command_name = u'flocker-deploy'


class DeployOptionsTests(StandardOptionsTestsMixin, SynchronousTestCase):
    """Tests for :class:`DeployOptions`."""
    options = DeployOptions

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
                                      [deploy, app])
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
                                      [deploy, app])
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
            UsageError, options.parseOptions, [deploy.path, app.path])

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
            UsageError, options.parseOptions, [deploy.path, app.path])

        expected = (
            "Application configuration at {path} could not be parsed "
            "as YAML"
        ).format(path=app.path)
        self.assertTrue(str(e).startswith(expected))

    def test_config_must_be_valid(self):
        """
        A ``UsageError`` is raised if any of the configuration is invalid.
        """
        options = self.options()
        deploy = FilePath(self.mktemp())
        app = FilePath(self.mktemp())

        deploy.setContent(b"{}")
        app.setContent(b"{}")

        self.assertRaises(
            UsageError, options.parseOptions, [deploy.path, app.path])

    def test_deployment_object(self):
        """
        A ``Deployment`` object is assigned to the ``Options`` instance.
        """
        db = Application(
            name=u'mysql-hybridcluster',
            image=DockerImage(
                repository=u'hybridlogic/mysql5.9', tag=u'latest'),
        )
        site = Application(
            name=u'site-hybridcluster.com',
            image=DockerImage(
                repository=u'hybridlogic/nginx', tag=u'v1.2.3'),
        )

        node1 = Node(hostname=u'node1.test', applications=frozenset([db]))
        node2 = Node(hostname=u'node2.test', applications=frozenset([site]))

        options = self.options()
        deployment_configuration_path = self.mktemp()
        deployment_configuration = FilePath(deployment_configuration_path)
        deployment_configuration.setContent(safe_dump(dict(
            version=1,
            nodes={'node1.test': [db.name], 'node2.test': [site.name]},
            )))

        application_configuration_path = self.mktemp()
        application_configuration = FilePath(application_configuration_path)
        application_configuration.setContent(safe_dump(dict(
            version=1,
            applications={
                db.name: dict(
                    image=u"{}:{}".format(
                        db.image.repository, db.image.tag)),
                site.name: dict(
                    image=u"{}:{}".format(
                        site.image.repository, site.image.tag)),
            })))

        options.parseOptions(
            [deployment_configuration_path, application_configuration_path])
        expected = Deployment(nodes=frozenset([node1, node2]))

        self.assertEqual(expected, options['deployment'])


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
            deployment_config_path.path, application_config_path.path])

        script = DeployScript()
        dummy_reactor = object()

        self.assertEqual(
            None,
            self.successResultOf(script.main(dummy_reactor, options))
        )

    def test_get_destinations(self):
        """
        ``DeployScript._get_destinations`` uses the hostnames in the deployment
        to create SSH ``INode`` destinations, returning them along with their
        target hostnames.
        """
        db = Application(
            name=u"db-example",
            image=DockerImage(repository=u"clusterhq/example"))

        node1 = Node(
            hostname=u"node101.example.com",
            applications=frozenset({db}))
        node2 = Node(
            hostname=u"node102.example.com",
            applications=frozenset({db}))

        id_rsa_flocker = DEFAULT_SSH_DIRECTORY.child(b"id_rsa_flocker")

        script = DeployScript()
        deployment = Deployment(nodes={node1, node2})
        destinations = script._get_destinations(deployment)

        def node(hostname):
            return ProcessNode.using_ssh(
                hostname, 22, b"root", id_rsa_flocker)

        self.assertEqual(
            {
                (node1.hostname, node(node1.hostname)),
                (node2.hostname, node(node2.hostname))
            },
            set(destinations))

    def run_script(self, alternate_destinations):
        """
        Run ``DeployScript.main`` with overridden destinations for
        ``flocker-changestate``.

        :param list alternate_destinations: ``INode`` providers to connect
             to instead of the default SSH-based ``ProcessNode``.

        :return: ``Deferred`` that fires with result of ``DeployScript.main``.
        """
        site = u"site-example.com"
        db = u"db-example.com"
        self.application_config = safe_dump({
            u"version": 1,
            u"applications": {
                site: {
                    u"image": u"clusterhq/example-site",
                },
                db: {
                    u"image": u"clusterhq/example-db",
                },
            },
        })

        self.deployment_config = safe_dump({
            u"version": 1,
            u"nodes": {
                u"node101.example.com": [site],
                u"node102.example.com": [db],
            },
        })

        temp = FilePath(self.mktemp())
        temp.makedirs()

        application_config_path = temp.child(b"app.yml")
        application_config_path.setContent(self.application_config)

        deployment_config_path = temp.child(b"deploy.yml")
        deployment_config_path.setContent(self.deployment_config)

        options = DeployOptions()
        options.parseOptions([
            deployment_config_path.path, application_config_path.path])

        # Change destination of commands:
        script = DeployScript()
        script._get_destinations = lambda nodes: alternate_destinations

        # Disable SSH configuration:
        script._configure_ssh = lambda deployment: succeed(None)

        return script.main(reactor, options)

    def test_calls_changestate(self):
        """
        ``DeployScript.main`` calls ``flocker-changestate`` using the
        destinations from ``_get_destinations``.
        """
        destinations = [
            (b'node101.example.com', FakeNode([b""])),
            (b'node102.example.com', FakeNode([b""])),
        ]
        running = self.run_script(destinations)

        def ran(ignored):
            expected1 = [
                b"flocker-changestate", self.deployment_config,
                self.application_config, b"node101.example.com"]

            expected2 = [
                b"flocker-changestate", self.deployment_config,
                self.application_config, b"node102.example.com"]

            self.assertEqual(
                list(node.remote_command for hostname, node in destinations),
                [expected1, expected2])
        running.addCallback(ran)
        return running

    def test_calls_changestate_in_thread_pool(self):
        """
        ``DeployScript.main`` calls ``flocker-changestate`` to destination
        nodes in a thread pool.

        (Proving actual parallelism is much more difficult...)
        """
        destinations = [
            (b'node101.example.com', FakeNode([b""])),
            (b'node102.example.com', FakeNode([b""])),
        ]

        running = self.run_script(destinations)

        def ran(ignored):
            self.assertNotEqual(
                set(node.thread_id for hostname, node in destinations),
                set([current_thread().ident]))
        running.addCallback(ran)
        return running
