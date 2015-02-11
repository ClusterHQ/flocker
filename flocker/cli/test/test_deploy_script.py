# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Unit tests for the implementation ``flocker-deploy``.
"""

from yaml import safe_dump, safe_load
from threading import current_thread

from twisted.python.filepath import FilePath
from twisted.python.usage import UsageError
from twisted.trial.unittest import TestCase, SynchronousTestCase
from twisted.internet.defer import succeed
from twisted.internet import reactor

from ...testtools import (
    FlockerScriptTestsMixin, StandardOptionsTestsMixin, make_with_init_tests)
from ..script import DeployScript, DeployOptions, NodeTarget
from .._sshconfig import DEFAULT_SSH_DIRECTORY
from ...control import Application, Deployment, DockerImage, Node
from ...common import ProcessNode, FakeNode


class NodeTargetInitTests(
    make_with_init_tests(
        record_type=NodeTarget,
        kwargs=dict(node=FakeNode(b''), hostname=u'node1.example.com')
    )
):
    """
    Tests for ``NodeTarget`` initialiser and attributes.
    """


class NodeTargetTests(SynchronousTestCase):
    """
    Tests for ``NodeTarget``.
    """
    def test_repr(self):
        """
        ``NodeTarget.__repr__`` includes the node and hostname.
        """
        self.assertEqual(
            "<NodeTarget(node=None, hostname=u'node1.example.com')>",
            repr(NodeTarget(node=None, hostname=u'node1.example.com'))
        )


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

    def test_config_fig_format(self):
        """
        A Fig compatible configuration passed via the command line is
        parsed by the ``FigConfiguration`` parser.
        """
        options = self.options()
        deploy = FilePath(self.mktemp())
        app = FilePath(self.mktemp())

        deploy.setContent(b"nodes:\n  node1.test: [postgres]\nversion: 1\n")
        app.setContent(b"{'postgres': {'image': 'sample/postgres'}}")
        options.parseOptions([deploy.path, app.path])

    def test_config_must_be_valid_format(self):
        """
        A ``UsageError`` is raised if the application configuration cannot
        be detected as any supported valid format.
        """
        options = self.options()
        deploy = FilePath(self.mktemp())
        app = FilePath(self.mktemp())

        deploy.setContent(b"{}")
        app.setContent(b"{'randomkey':'somevalue', 'x':'y', 'z':3}")

        e = self.assertRaises(
            UsageError, options.parseOptions, [deploy.path, app.path])
        self.assertEqual(
            e.message,
            "Configuration is not a valid Fig or Flocker format."
        )

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
            ports=frozenset(),
            links=frozenset(),
        )
        site = Application(
            name=u'site-hybridcluster.com',
            image=DockerImage(
                repository=u'hybridlogic/nginx', tag=u'v1.2.3'),
            ports=frozenset(),
            links=frozenset(),
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

    def test_config_fig_converted_to_flocker_yaml(self):
        """
        A Fig-compatible application configuration is converted to its
        equivalent Flocker configuration before being passed to
        ``DeployScript.main``
        """
        options = self.options()

        deploy = FilePath(self.mktemp())
        app = FilePath(self.mktemp())

        deploy.setContent(b"nodes:\n  node1.test: [postgres]\nversion: 1\n")

        fig_config = (
            b"postgres:\n"
            "  image: sample/postgres\n"
            "  environment:\n"
            "    PGSQL_PASSWORD: clusterhq\n"
            "  ports:\n"
            "    - \"5432:5432\"\n"
            "  volumes:\n"
            "    - /var/lib/pgsql\n"
        )
        app.setContent(fig_config)

        expected_dict = {
            'version': 1,
            'applications': {
                'postgres': {
                    'image': 'sample/postgres:latest',
                    'environment': {'PGSQL_PASSWORD': 'clusterhq'},
                    'ports': [{'internal': 5432, 'external': 5432}],
                    'volume': {'mountpoint': '/var/lib/pgsql'},
                    'restart_policy': {'name': 'never'},
                }
            }
        }

        options.parseOptions([deploy.path, app.path])

        self.assertEqual(
            safe_load(options['application_config']),
            expected_dict
        )


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
            return NodeTarget(
                node=ProcessNode.using_ssh(
                    hostname, 22, b"root", id_rsa_flocker),
                hostname=hostname)

        self.assertEqual(
            {node(node1.hostname), node(node2.hostname)},
            set(destinations))

    def run_script(self, alternate_destinations):
        """
        Run ``DeployScript.main`` with overridden destinations for
        ``flocker-changestate`` and ``flocker-reportstate``.

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

    def test_calls_reportstate(self):
        """
        ``DeployScript.main`` calls ``flocker-reportstatestate`` using the
        destinations and hostnames from ``_get_destinations``.
        """
        # Make sure we're inspecting results on reportstate calls only:
        self.patch(DeployScript, "_changestate_on_nodes", lambda *args: None)

        expected_hostname1 = b'node101.example.com'
        expected_hostname2 = b'node102.example.com'

        destinations = [
            NodeTarget(node=FakeNode([b"{}"]), hostname=expected_hostname1),
            NodeTarget(node=FakeNode([b"{}"]), hostname=expected_hostname2),
        ]
        running = self.run_script(destinations)

        def ran(ignored):
            expected_command = [b"flocker-reportstate"]

            self.assertEqual(
                list(target.node.remote_command for target in destinations),
                [expected_command, expected_command],
            )
        running.addCallback(ran)
        return running

    def test_calls_reportstate_in_thread_pool(self):
        """
        ``DeployScript.main`` calls ``flocker-reportstate`` to destination
        nodes in a thread pool.

        (Proving actual parallelism is much more difficult...)
        """
        # Make sure we're inspecting results on reportstate calls only:
        self.patch(DeployScript, "_changestate_on_nodes", lambda *args: None)

        destinations = [
            NodeTarget(node=FakeNode([b"{}"]),
                       hostname=b'node101.example.com'),
            NodeTarget(node=FakeNode([b"{}"]),
                       hostname=b'node102.example.com'),
        ]

        running = self.run_script(destinations)

        def ran(ignored):
            self.assertNotEqual(
                set(target.node.thread_id for target in destinations),
                set([current_thread().ident]))
        running.addCallback(ran)
        return running

    def test_reportstate_failure_means_no_changestate(self):
        """
        If ``flocker-reportstate`` fails to respond for some reason,
        ``flocker-changestate`` is not called.
        """
        # If this is ever called we'll get a ZeroDivisionError:
        self.patch(DeployScript, "_changestate_on_nodes", lambda *args: 1/0)

        exception = RuntimeError()
        destinations = [
            NodeTarget(node=FakeNode([exception]),
                       hostname=b'node101.example.com'),
            NodeTarget(node=FakeNode([b"{}"]),
                       hostname=b'node102.example.com'),
        ]
        running = self.run_script(destinations)
        self.assertFailure(running, RuntimeError)
        return running

    def test_calls_changestate(self):
        """
        ``DeployScript.main`` calls ``flocker-changestate`` using the
        destinations and hostnames from ``_get_destinations`` and the
        aggreggated result for ``flocker-reportstate``.
        """
        expected_hostname1 = b'node101.example.com'
        expected_hostname2 = b'node102.example.com'

        actual_config_host1 = {
            u"version": 1,
            u"applications": {
                u"db-example.com": {
                    u"image": u"clusterhq/example-db",
                },
            },
        }
        actual_config_host2 = {
            u"version": 1,
            u"applications": {
                u"site-example.com": {
                    u"image": u"clusterhq/example-site",
                },
            },
        }

        destinations = [
            NodeTarget(node=FakeNode([safe_dump(actual_config_host1), b""]),
                       hostname=expected_hostname1),
            NodeTarget(node=FakeNode([safe_dump(actual_config_host2), b""]),
                       hostname=expected_hostname2),
        ]
        running = self.run_script(destinations)

        def ran(ignored):
            expected_common = [
                b"flocker-changestate",
                safe_load(self.deployment_config),
                safe_load(self.application_config),
                {expected_hostname1: actual_config_host1,
                 expected_hostname2: actual_config_host2}]

            actual = []
            for target in destinations:
                command = target.node.remote_command
                actual.append(map(safe_load, command[:-1]) + [command[-1]])
            self.assertEqual(
                sorted(actual),
                sorted([expected_common + [expected_hostname1],
                        expected_common + [expected_hostname2]])
            )
        running.addCallback(ran)
        return running

    def test_calls_changestate_in_thread_pool(self):
        """
        ``DeployScript.main`` calls ``flocker-changestate`` to destination
        nodes in a thread pool.

        (Proving actual parallelism is much more difficult...)
        """
        destinations = [
            NodeTarget(node=FakeNode([b"{}", b""]),
                       hostname=b'node101.example.com'),
            NodeTarget(node=FakeNode([b"{}", b""]),
                       hostname=b'node102.example.com'),
        ]

        running = self.run_script(destinations)

        def ran(ignored):
            self.assertNotEqual(
                set(target.node.thread_id for target in destinations),
                set([current_thread().ident]))
        running.addCallback(ran)
        return running
