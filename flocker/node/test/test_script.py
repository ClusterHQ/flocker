# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for :module:`flocker.node.script`.
"""

from StringIO import StringIO

from pyrsistent import pmap

from twisted.trial.unittest import SynchronousTestCase
from twisted.python.usage import UsageError
from twisted.python.filepath import FilePath
from twisted.application.service import Service

from yaml import safe_dump, safe_load
from ...testtools import StandardOptionsTestsMixin, MemoryCoreReactor
from ...volume.testtools import make_volume_options_tests
from ...route import make_memory_network

from ..script import (
    ZFSAgentOptions, ZFSAgentScript,
    ChangeStateOptions, ChangeStateScript,
    ReportStateOptions, ReportStateScript)
from .. import script as script_module
from .._docker import FakeDockerClient, Unit
from ...control._model import (
    Application, Deployment, DockerImage, Node, AttachedVolume, Dataset,
    Manifestation)
from ...control._config import dataset_id_from_name
from .._loop import AgentLoopService
from .._deploy import P2PNodeDeployer

from ...volume.testtools import create_volume_service


class ChangeStateScriptTests(SynchronousTestCase):
    """
    Tests for ``ChangeStateScript``.
    """
    def test_deployer_docker_client(self):
        """
        ``ChangeState._docker_client`` is configured with the default docker
        client.
        """
        self.assertIs(None, ChangeStateScript()._docker_client)


class ChangeStateScriptMainTests(SynchronousTestCase):
    """
    Tests for ``ChangeStateScript.main``.
    """
    def test_main_calls_deployer_change_node_state(self):
        """
        ``ChangeStateScript.main`` calls ``change_node_state`` with
        the ``Deployment`` and `hostname` supplied on the command line.
        """
        script = ChangeStateScript()

        change_node_state_calls = []

        def spy_change_node_state(
                deployer, desired_state, current_cluster_state):
            """
            A stand in for ``Deployer.change_node_state`` which records calls
            made to it.
            """
            change_node_state_calls.append((desired_state,
                                            current_cluster_state,
                                            deployer.hostname))

        self.patch(
            script_module, 'change_node_state', spy_change_node_state)

        expected_deployment = object()
        expected_current = object()
        expected_hostname = b'node1.example.com'
        options = dict(deployment=expected_deployment,
                       current=expected_current,
                       hostname=expected_hostname)
        script.main(
            reactor=object(), options=options, volume_service=Service())

        self.assertEqual(
            [(expected_deployment, expected_current, expected_hostname)],
            change_node_state_calls
        )


class StandardChangeStateOptionsTests(
        make_volume_options_tests(
            ChangeStateOptions, extra_arguments=[
                safe_dump(dict(version=1, nodes={})),
                safe_dump(dict(version=1, applications={})),
                safe_dump({}),
                b"node001",
            ])):
    """
    Tests for the volume configuration arguments of ``ChangeStateOptions``.
    """


class ChangeStateOptionsTests(StandardOptionsTestsMixin, SynchronousTestCase):
    """
    Tests for :class:`ChangeStateOptions`.
    """
    options = ChangeStateOptions

    def test_custom_configs(self):
        """
        The supplied application and deployment configuration strings are
        parsed as a :class:`Deployment` on the options instance.
        """
        application = Application(
            name=u'mysql-hybridcluster',
            image=DockerImage(repository=u'hybridlogic/mysql5.9',
                              tag=u'latest'),
            ports=frozenset(),
            links=frozenset(),
            )

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

        current_config = {'node2.example.com': {
            'applications': {
                'mysql-something': {
                    'image': 'unknown',
                    'volume': {'mountpoint': b'/var/lib/data'},
                }
            },
            'version': 1
        }}

        options.parseOptions(
            [safe_dump(deployment_config),
             safe_dump(application_config),
             safe_dump(current_config),
             b'node1.example.com'])

        self.assertEqual(
            Deployment(nodes=frozenset([node])), options['deployment'])

    def test_current_configuration(self):
        """
        The supplied current cluster configuration strings is parsed as a
        :class:`Deployment` on the options instance.
        """
        options = self.options()
        deployment_config = {"nodes": {},
                             "version": 1}

        application_config = dict(
            version=1,
            applications={},
        )

        current_config = {'node2.example.com': {
            'applications': {
                'mysql-something': {
                    'image': 'unknown',
                    'volume': {'mountpoint': b'/var/lib/data'},
                }
            },
            'version': 1
        }}

        expected_current_config = Deployment(nodes=frozenset([
            Node(hostname='node2.example.com', applications=frozenset([
                Application(
                    name='mysql-something',
                    image=DockerImage.from_string('unknown'),
                    ports=frozenset(),
                    links=frozenset(),
                    volume=AttachedVolume(
                        manifestation=Manifestation(
                            dataset=Dataset(
                                dataset_id=dataset_id_from_name(
                                    "mysql-something"),
                                metadata=pmap({'name': 'mysql-something'})),
                            primary=True),
                        mountpoint=FilePath(b'/var/lib/data'),
                    )
                ),
            ]))]))

        options.parseOptions(
            [safe_dump(deployment_config),
             safe_dump(application_config),
             safe_dump(current_config),
             b'node1.example.com'])

        self.assertEqual(expected_current_config, options['current'])

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
            [safe_dump(deployment_config), safe_dump({}), safe_dump({}),
             b'node1.example.com']
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
            [deployment_bad_yaml, b'', b'{}', b'node1.example.com'])

        # See https://clusterhq.atlassian.net/browse/FLOC-282 for more complete
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
            [b'', application_bad_yaml, b'{}', b'node1.example.com'])

        # See https://clusterhq.atlassian.net/browse/FLOC-282 for more complete
        # testing of this string.
        self.assertTrue(
            str(e).startswith('Application config could not be parsed as YAML')
        )

    def test_invalid_current_yaml(self):
        """
        If the supplied current config is not valid `YAML`, a
        ``UsageError`` is raised.
        """
        options = self.options()
        bad_yaml = "{'foo':'bar', 'x':y, '':'"
        e = self.assertRaises(
            UsageError, options.parseOptions,
            [b'', b'', bad_yaml, b'node1.example.com'])

        # See https://clusterhq.atlassian.net/browse/FLOC-282 for more complete
        # testing of this string.
        self.assertTrue(
            str(e).startswith('Current config could not be parsed as YAML')
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
             b'{}',
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
             b'{}',
             hostname]
        )

        self.assertEqual(
            "Non-ASCII hostname: {hostname}".format(hostname=hostname),
            str(e)
        )


class StandardReportStateOptionsTests(
        make_volume_options_tests(ReportStateOptions)):
    """
    Tests for the volume configuration arguments of ``ReportStateOptions``.
    """


class ReportStateOptionsTests(StandardOptionsTestsMixin, SynchronousTestCase):
    """
    Tests for :class:`ReportStateOptions`.
    """
    options = ReportStateOptions

    def test_no_options(self):
        """
        ``ReportStateOptions`` can instantiate and successfully parse
        without any (non-standard) options.
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


class ReportStateScriptMainTests(SynchronousTestCase):
    """
    Tests for ``ReportStateScript.main``.
    """
    def test_yaml_output(self):
        """
        ``ReportStateScript.main`` returns a deferred which fires after the
        YAML representation of the node state, including applications (running
        or not) and used TCP port numbers from
        ``Deployer.discover_node_configuration``, have been written to stdout.
        """
        unit1 = Unit(name=u'site-example.com',
                     container_name=u'site-example.com',
                     container_image=u'clusterhq/wordpress:latest',
                     activation_state=u'active')
        unit2 = Unit(name=u'site-example.net',
                     container_name=u'site-example.net',
                     container_image=u'clusterhq/wordpress:latest',
                     activation_state=u'inactive')
        units = {unit1.name: unit1, unit2.name: unit2}

        fake_docker = FakeDockerClient(units=units)

        used_ports = frozenset([1, 10, 200, 52000])
        network = make_memory_network(used_ports=used_ports)

        expected = {
            'used_ports': sorted(used_ports),
            'applications': {
                'site-example.net': {
                    'image': unit2.container_image,
                    'restart_policy': {'name': 'never'},
                },
                'site-example.com': {
                    'image': unit1.container_image,
                    'restart_policy': {'name': 'never'},
                }
            },
            'version': 1,
        }

        script = ReportStateScript(fake_docker, network)
        content = StringIO()
        self.patch(script, '_stdout', content)
        script.main(
            reactor=object(), options=[],
            volume_service=create_volume_service(self))
        self.assertEqual(safe_load(content.getvalue()), expected)


class ZFSAgentScriptTests(SynchronousTestCase):
    """
    Tests for ``ZFSAgentScript``.
    """
    def test_main_starts_service(self):
        """
        ``ZFSAgentScript.main`` starts the given service.
        """
        service = Service()
        options = ZFSAgentOptions()
        options.parseOptions([b"1.2.3.4", b"example.com"])
        ZFSAgentScript().main(MemoryCoreReactor(), options, service)
        self.assertTrue(service.running)

    def test_no_immediate_stop(self):
        """
        The ``Deferred`` returned from ``ZFSAgentScript`` is not fired.
        """
        script = ZFSAgentScript()
        options = ZFSAgentOptions()
        options.parseOptions([b"1.2.3.4", b"example.com"])
        self.assertNoResult(script.main(MemoryCoreReactor(), options,
                                        Service()))

    def test_starts_convergence_loop(self):
        """
        ``ZFSAgentScript.main`` starts a convergence loop service.
        """
        service = Service()
        options = ZFSAgentOptions()
        options.parseOptions([b"--destination-port", b"1234", b"1.2.3.4",
                              b"example.com"])
        test_reactor = MemoryCoreReactor()
        ZFSAgentScript().main(test_reactor, options, service)
        parent_service = service.parent
        # P2PNodeDeployer is difficult to compare automatically, so do so
        # manually:
        deployer = parent_service.deployer
        parent_service.deployer = None
        self.assertEqual((parent_service, deployer.__class__,
                          deployer.hostname, deployer.volume_service,
                          parent_service.running),
                         (AgentLoopService(reactor=test_reactor,
                                           deployer=None,
                                           host=u"example.com",
                                           port=1234),
                          P2PNodeDeployer, b"1.2.3.4", service, True))


class ZFSAgentOptionsTests(make_volume_options_tests(
        ZFSAgentOptions, [b"1.2.3.4", b"example.com"])):
    """
    Tests for the volume configuration arguments of ``ZFSAgentOptions``.
    """
    def test_default_port(self):
        """
        The default AMP destination port configured by ``ZFSAgentOptions`` is
        4524.
        """
        options = ZFSAgentOptions()
        options.parseOptions([b"1.2.3.4", b"example.com"])
        self.assertEqual(options["destination-port"], 4524)

    def test_custom_port(self):
        """
        The ``--destination-port`` command-line option allows configuring the
        destination port.
        """
        options = ZFSAgentOptions()
        options.parseOptions([b"--destination-port", b"1234",
                              b"1.2.3.4", b"example.com"])
        self.assertEqual(options["destination-port"], 1234)

    def test_host(self):
        """
        The second required command-line argument allows configuring the
        destination host.
        """
        options = ZFSAgentOptions()
        options.parseOptions([b"1.2.3.4", b"control.example.com"])
        self.assertEqual(options["destination-host"], u"control.example.com")

    def test_hostname(self):
        """
        The first required command-line argument allows configuring the
        hostname of the node the agent is operating on.
        """
        options = ZFSAgentOptions()
        options.parseOptions([b"5.6.7.8", b"control.example.com"])
        self.assertEqual(options["hostname"], u"5.6.7.8")
