# Copyright ClusterHQ Inc.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_script,flocker.node.functional.test_script -*- # noqa

"""
The command-line ``flocker-*-agent`` tools.
"""

from socket import socket
from contextlib import closing
import sys
from time import sleep

import yaml

from jsonschema import FormatChecker, Draft4Validator

from pyrsistent import PClass, field, PMap, pmap

from eliot import ActionType, fields

from zope.interface import implementer

from twisted.python.filepath import FilePath
from twisted.python.usage import Options, UsageError
from twisted.internet.ssl import Certificate
from twisted.internet import reactor  # pylint: disable=unused-import
from twisted.internet.defer import succeed


from ..common.script import (
    ICommandLineScript,
    flocker_standard_options, FlockerScriptRunner, main_for_service)
from ..common.plugin import PluginLoader
from . import P2PManifestationDeployer, ApplicationNodeDeployer
from ._loop import AgentLoopService
from .exceptions import StorageInitializationError
from .diagnostics import (
    current_distribution, FlockerDebugArchive, DISTRIBUTION_BY_LABEL,
    lookup_distribution,
)
from .agents.blockdevice import (
    BlockDeviceDeployer, ProcessLifetimeCache,
)
from ..ca import ControlServicePolicy, NodeCredential
from ..common._era import get_era

from .backends import DeployerType, backend_loader

__all__ = [
    "flocker_dataset_agent_main",
    "flocker_container_agent_main",
    "flocker_diagnostics_main",
]


def flocker_dataset_agent_main():
    """
    Implementation of the ``flocker-dataset-agent`` command line script.

    This starts a dataset convergence agent.  It currently supports only a
    small number of hard-coded storage drivers.  Later it will be capable of
    starting a dataset agent using any Flocker-supplied storage driver any
    third-party drivers via plugins.
    """
    service_factory = DatasetServiceFactory()
    agent_script = AgentScript(service_factory=service_factory.get_service)
    options = DatasetAgentOptions()

    return FlockerScriptRunner(
        script=agent_script,
        options=options,
    ).main()


def flocker_container_agent_main():
    """
    Implementation of the ``flocker-container-agent`` command line script.

    This starts a Docker-based container convergence agent.
    """
    def deployer_factory(cluster_uuid, **kwargs):
        return ApplicationNodeDeployer(**kwargs)
    service_factory = AgentServiceFactory(
        deployer_factory=deployer_factory
    ).get_service
    agent_script = AgentScript(service_factory=service_factory)
    return FlockerScriptRunner(
        script=agent_script,
        options=ContainerAgentOptions()
    ).main()


LOG_GET_EXTERNAL_IP = ActionType(u"flocker:node:script:get_external_ip",
                                 fields(host=unicode, port=int),
                                 fields(local_ip=unicode),
                                 "An attempt to discover the local IP.")


def _get_external_ip(host, port):
    """
    Get an external IP address for this node that can in theory connect to
    the given host and port.

    Failures are retried until a successful connect.

    See https://clusterhq.atlassian.net/browse/FLOC-1751 for a possibly
    better solution.

    :param host: A host to connect to.
    :param port: The port to connect to.

    :return unicode: IP address of external interface on this node.
    """
    while True:
        try:
            with LOG_GET_EXTERNAL_IP(host=unicode(host), port=port) as ctx:
                with closing(socket()) as sock:
                    sock.connect((host, port))
                    result = unicode(sock.getsockname()[0], "ascii")
                    ctx.addSuccessFields(local_ip=result)
                    return result
        except:
            # Error is logged by LOG_GET_EXTERNAL_IP.
            sleep(0.1)


class _TLSContext(PClass):
    """
    Information extracted from the TLS certificates for this node.

    :ivar context_factory: A TLS
        context factory will validate the control service and present
        the node's certificate to the control service.

    :ivar NodeCredential node_credential: The node's certificate information.
    """
    context_factory = field(mandatory=True)
    node_credential = field(mandatory=True)


def _context_factory_and_credential(path, host, port):
    """
    Load a TLS context factory for the AMP client from the path where
    configuration and certificates live.

    The CA certificate and node private key and certificate are expected
    to be siblings of the configuration file.

    :param FilePath path: Path to directory where configuration lives.
    :param bytes host: The host we will be connecting to.
    :param int port: The port we will be connecting to.

    :return: ``_TLSContext`` instance.
    """
    ca = Certificate.loadPEM(path.child(b"cluster.crt").getContent())
    # This is a hack; from_path should be more
    # flexible. https://clusterhq.atlassian.net/browse/FLOC-1865
    node_credential = NodeCredential.from_path(path, b"node")
    policy = ControlServicePolicy(
        ca_certificate=ca, client_credential=node_credential.credential)
    return _TLSContext(context_factory=policy.creatorForNetloc(host, port),
                       node_credential=node_credential)


def validate_configuration(configuration):
    """
    Validate a provided configuration.

    XXX: Validation of backend specific parameters was removed in
    a4d0f0eb4c38ffbfe10085a1cbc3d5ed5cae17c7 and will be re-instated
    as part of FLOC-2058.

    :param dict configuration: A desired configuration for an agent.

    :raises: jsonschema.ValidationError if the configuration is invalid.
    """
    schema = {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "type": "object",
        "required": ["version", "control-service", "dataset"],
        "properties": {
            "version": {
                "type": "number",
                "maximum": 1,
                "minimum": 1,
            },
            "control-service": {
                "type": "object",
                "required": ["hostname"],
                "properties": {
                    "hostname": {
                        "type": "string",
                        "format": "hostname",
                    },
                    "port": {"type": "integer"},
                }
            },
            "dataset": {
                "type": "object",
                "properties": {
                    "backend": {
                        "type": "string",
                    },
                },
                "required": [
                    "backend",
                ],
            },
            "logging": {
                # Format described at https://www.python.org/dev/peps/pep-0391/
                "type": "object",
            },
        }
    }

    v = Draft4Validator(schema, format_checker=FormatChecker())
    v.validate(configuration)


@flocker_standard_options
class _AgentOptions(Options):
    """
    Command line options for agents.
    """
    # Use as basis for subclass' synopsis:
    synopsis = "Usage: {} [OPTIONS]"

    optParameters = [
        ["agent-config", "c", "/etc/flocker/agent.yml",
         "The configuration file to set the node service."],
    ]

    def postOptions(self):
        self['agent-config'] = FilePath(self['agent-config'])


class DatasetAgentOptions(_AgentOptions):
    """
    Command line options for ``flocker-dataset-agent``.
    """
    longdesc = """\
    flocker-dataset-agent runs a dataset convergence agent on a node.
    """

    synopsis = _AgentOptions.synopsis.format("flocker-dataset-agent")


class ContainerAgentOptions(_AgentOptions):
    """
    Command line options for ``flocker-container-agent``.
    """
    longdesc = """\
    flocker-container-agent runs a container convergence agent on a node.
    """

    synopsis = _AgentOptions.synopsis.format("flocker-container-agent")


@implementer(ICommandLineScript)
class AgentScript(PClass):
    """
    Implement top-level logic for the ``flocker-dataset-agent`` and
    ``flocker-container-agent`` scripts.

    :ivar service_factory: A two-argument callable that returns an ``IService``
        provider that will get run when this script is run.  The arguments
        passed to it are the reactor being used and a ``AgentOptions``
        instance which has parsed any command line options that were given.
    """
    service_factory = field(mandatory=True)

    def main(self, reactor, options):
        return main_for_service(
            reactor,
            self.service_factory(reactor, options)
        )


class AgentServiceFactory(PClass):
    """
    Implement general agent setup in a way that's usable by
    ``AgentScript`` but also easily testable.

    Possibly ``ICommandLineScript`` should be replaced by something that is
    inherently more easily tested so that this separation isn't required.

    :ivar deployer_factory: A two-argument callable to create an
        ``IDeployer`` provider for this script.  The arguments are a
        ``hostname`` keyword argument, a ``cluster_uuid`` keyword and a
        ``node_uuid`` keyword argument. They must be passed by keyword.
    :ivar get_external_ip: Typically ``_get_external_ip``, but
        overrideable for tests.
    """
    # This should have an explicit interface:
    # https://clusterhq.atlassian.net/browse/FLOC-1929
    deployer_factory = field(mandatory=True)
    get_external_ip = field(initial=(lambda: _get_external_ip), mandatory=True)

    def get_service(self, reactor, options):
        """
        Create an ``AgentLoopService`` instance.

        :param reactor: The reactor to give to the service so it can schedule
            timed events and make network connections.

        :param AgentOptions options: The command-line options to use to
            configure the loop and the loop's deployer.

        :param context_factory: TLS context factory to pass to service.

        :param NodeCredential node_credential: The node credential.

        :return: The ``AgentLoopService`` instance.
        """
        configuration = get_configuration(options)
        host = configuration['control-service']['hostname']
        port = configuration['control-service']['port']
        ip = self.get_external_ip(host, port)

        tls_info = _context_factory_and_credential(
            options["agent-config"].parent(), host, port)

        return AgentLoopService(
            reactor=reactor,
            deployer=self.deployer_factory(
                node_uuid=tls_info.node_credential.uuid, hostname=ip,
                cluster_uuid=tls_info.node_credential.cluster_uuid),
            host=host, port=port,
            context_factory=tls_info.context_factory,
            era=get_era(),
        )


def get_configuration(options):
    """
    Load and validate the configuration in the file specified by the given
    options.

    :param DatasetAgentOptions options: The dataset agent options specifying
        the location of the configuration.

    :return: A ``dict`` representing the configuration loaded from the file.
    """
    agent_config = options[u'agent-config']
    configuration = yaml.safe_load(agent_config.getContent())

    validate_configuration(configuration=configuration)

    configuration['control-service'].setdefault('port', 4524)

    path = agent_config.parent()
    # This is a hack; from_path should be more
    # flexible. https://clusterhq.atlassian.net/browse/FLOC-1865
    configuration['ca-certificate'] = Certificate.loadPEM(
        path.child(b"cluster.crt").getContent())
    configuration['node-credential'] = NodeCredential.from_path(path, b"node")

    return configuration


_DEFAULT_DEPLOYERS = {
    DeployerType.p2p: lambda api, **kw:
        P2PManifestationDeployer(volume_service=api, **kw),
    DeployerType.block: lambda api, **kw:
        BlockDeviceDeployer(block_device_api=ProcessLifetimeCache(api),
                            _underlying_blockdevice_api=api,
                            **kw),
}


def get_api(backend, api_args, reactor, cluster_id):
    """
    Get an storage driver which can be used to create an ``IDeployer``.

    :param BackendDescription backend: Backend to use.
    :param PMap api_args: Parameters to pass the API factory.
    :param reactor: The reactor to use.
    :param cluster_id: The cluster's unique ID.

    :return: An object created by one of the factories in ``self.backends``
        using the configuration from ``self.api_args`` and other useful
        state on ``self``.
    """
    if backend.needs_cluster_id:
        api_args = api_args.set("cluster_id", cluster_id)
    if backend.needs_reactor:
        api_args = api_args.set("reactor", reactor)

    for config_key in backend.required_config:
        if config_key not in api_args:
            raise UsageError(
                u"Configuration error: Required key {} is missing.".format(
                    config_key.decode("utf-8"))
            )

    try:
        return backend.api_factory(**api_args)
    except StorageInitializationError as e:
        if e.code == StorageInitializationError.CONFIGURATION_ERROR:
            raise UsageError(u"Configuration error", *e.args)
        else:
            raise


class AgentService(PClass):
    """
    :cvar PluginLoader backends: Plugin loader to get dataset backend from.
    :ivar deployers: Factories to create ``IDeployer`` providers given an API
        object and some extra keyword arguments.  Keyed on a value from
        ``DeployerType``.
    :ivar node_credential: Credentials with which to configure this agent.
    :ivar ca_certificate: The root certificate to use to validate the control
        service certificate.
    :ivar backend_name: The name of the storage driver to instantiate.  This
        must name one of the items in ``backends``.
    :ivar api_args: Extra arguments to pass to the factory from ``backends``.
    :ivar get_external_ip: Typically ``_get_external_ip``, but
        overrideable for tests.
    """
    backends = field(
        PluginLoader,
        mandatory=True,
        initial=(lambda: backend_loader),
    )
    deployers = field(factory=pmap, initial=_DEFAULT_DEPLOYERS, mandatory=True)
    reactor = field(initial=reactor, mandatory=True)

    get_external_ip = field(initial=(lambda: _get_external_ip), mandatory=True)

    control_service_host = field(type=bytes, mandatory=True)
    control_service_port = field(type=int, mandatory=True)

    # Cannot use type=NodeCredential because one of the tests really wants to
    # set this to None.
    node_credential = field(mandatory=True)
    # Cannot use type=Certificate; pyrsistent rejects classic classes.
    ca_certificate = field(mandatory=True)

    backend_name = field(type=unicode, mandatory=True)
    api_args = field(type=PMap, factory=pmap, mandatory=True)

    @classmethod
    def from_configuration(cls, configuration):
        """
        Load configuration from a data structure loaded from the configuration
        file and only minimally processed.

        :param dict configuration: Agent configuration as returned by
            ``get_configuration``.

        :return: A new instance of ``cls`` with values loaded from the
            configuration.
        """
        if 'logging' in configuration:
            from logging.config import dictConfig
            dictConfig(configuration['logging'])

        host = configuration['control-service']['hostname']
        port = configuration['control-service']['port']

        node_credential = configuration['node-credential']
        ca_certificate = configuration['ca-certificate']

        api_args = configuration['dataset']
        backend_name = api_args.pop('backend')

        return cls(
            control_service_host=host,
            control_service_port=port,

            node_credential=node_credential,
            ca_certificate=ca_certificate,

            backend_name=backend_name.decode("ascii"),
            api_args=api_args,
        )

    def get_backend(self):
        """
        Find the backend in ``self.backends`` that matches the one named by
        ``self.backend_name``.

        :raise ValueError: If ``backend_name`` doesn't match any known backend.
        :return: The matching ``BackendDescription``.
        """
        return self.backends.get(self.backend_name)

    # Needs tests: FLOC-1964.
    def get_tls_context(self):
        """
        Get some TLS configuration objects which will authenticate this node to
        the control service node and the reverse.
        """
        policy = ControlServicePolicy(
            ca_certificate=self.ca_certificate,
            client_credential=self.node_credential.credential,
        )
        return _TLSContext(
            context_factory=policy.creatorForNetloc(
                self.control_service_host, self.control_service_port,
            ),
            node_credential=self.node_credential,
        )

    def get_api(self):
        """
        Get an storage driver which can be used to create an ``IDeployer``.

        :return: An object created by one of the factories in ``self.backends``
            using the configuration from ``self.api_args`` and other useful
            state on ``self``.
        """
        backend = self.get_backend()
        cluster_id = None
        if backend.needs_cluster_id:
            cluster_id = self.node_credential.cluster_uuid

        return get_api(backend, self.api_args, self.reactor, cluster_id)

    def get_deployer(self, api):
        """
        Create an ``IDeployer`` provider suitable for the configured backend
        and this node.

        :param api: The storage driver which will be supplied to the
            ``IDeployer`` factory defined by the ``BackendDescription``.

        :return: The ``IDeployer`` provider.
        """
        backend = self.get_backend()
        deployer_factory = self.deployers[backend.deployer_type]

        address = self.get_external_ip(
            self.control_service_host, self.control_service_port,
        )
        node_uuid = self.node_credential.uuid
        return deployer_factory(
            api=api, hostname=address, node_uuid=node_uuid,
        )

    def get_loop_service(self, deployer):
        """
        :param IDeployer deployer: The deployer which the loop service can use
            to interact with the system.

        :return: An ``AgentLoopService`` which will use the given deployer to
            discover changes to send to the control service and to deploy
            configuration changes received from the control service.
        """
        return AgentLoopService(
            reactor=self.reactor,
            deployer=deployer,
            host=self.control_service_host, port=self.control_service_port,
            context_factory=self.get_tls_context().context_factory,
            era=get_era(),
        )


class DatasetServiceFactory(PClass):
    """
    A helper for creating most of the pieces that go into a dataset convergence
    agent.
    """
    agent_service_factory = field(initial=(lambda: AgentService.from_configuration))
    configuration_factory = field(initial=(lambda: get_configuration))

    def get_service(self, reactor, options):
        """
        Create an ``AgentLoopService`` instance which will run a dataset
        convergence agent.
        """
        configuration = self.configuration_factory(options)

        agent_service = self.agent_service_factory(configuration)
        agent_service = agent_service.set(reactor=reactor)

        api = agent_service.get_api()

        deployer = agent_service.get_deployer(api)

        loop_service = agent_service.get_loop_service(deployer)

        return loop_service


@flocker_standard_options
class DiagnosticsOptions(Options):
    """
    Command line options for ``flocker-diagnostics``.
    """
    longdesc = """\
    Exports Flocker log files and diagnostic data. Run this script as root, on
    an Ubuntu 14.04 or Centos 7 server where the clusterhq-flocker-node package
    has been installed.
    """

    synopsis = "Usage: flocker-diagnostics [OPTIONS]"

    optParameters = [
        ["distribution-name", "d", "auto",
         "Force the use of ``distribution`` specific tools "
         "when gathering diagnostic information. "
         "One of {}".format(
             ', '.join(['auto'] + DISTRIBUTION_BY_LABEL.keys())
         )],
    ]

    def postOptions(self):
        distribution_name = self['distribution-name']
        if distribution_name is 'auto':
            distribution_name = current_distribution()

        distribution = lookup_distribution(distribution_name)

        if distribution is None:
            raise UsageError(
                "flocker-diagnostics "
                "is not supported on this distribution ({!r}).\n"
                "See https://docs.clusterhq.com/en/latest/using/administering/debugging.html \n"  # noqa
                "for alternative ways to export Flocker logs "
                "and diagnostic data.\n".format(distribution_name)
            )
        self.distribution = distribution


@implementer(ICommandLineScript)
class DiagnosticsScript(PClass):
    """
    Implement top-level logic for the ``flocker-diagnostics``.
    """
    def main(self, reactor, options):
        archive_path = FlockerDebugArchive(
            service_manager=options.distribution.service_manager(),
            log_exporter=options.distribution.log_exporter()
        ).create()
        sys.stdout.write(archive_path + '\n')
        return succeed(None)


def flocker_diagnostics_main():
    return FlockerScriptRunner(
        script=DiagnosticsScript(),
        options=DiagnosticsOptions(),
        logging=False,
    ).main()
