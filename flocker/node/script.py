# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_script,flocker.node.functional.test_script -*- # noqa

"""
The command-line ``flocker-*-agent`` tools.
"""

from socket import socket
from contextlib import closing
from time import sleep

import yaml

from jsonschema import FormatChecker, Draft4Validator

from pyrsistent import PRecord, field, PMap, pmap, pvector

from eliot import ActionType, fields

from zope.interface import implementer

from twisted.python.filepath import FilePath
from twisted.python.usage import Options
from twisted.internet.ssl import Certificate
from twisted.internet import reactor
from twisted.python.constants import Names, NamedConstant
from twisted.python.reflect import namedAny

from ..volume.filesystems import zfs
from ..volume.service import (
    VolumeService, DEFAULT_CONFIG_PATH, FLOCKER_MOUNTPOINT, FLOCKER_POOL)

from ..common.script import (
    ICommandLineScript,
    flocker_standard_options, FlockerScriptRunner, main_for_service)
from . import P2PManifestationDeployer, ApplicationNodeDeployer
from ._loop import AgentLoopService
from .agents.blockdevice import (
    LoopbackBlockDeviceAPI, BlockDeviceDeployer, ProcessLifetimeCache,
)
from ..ca import ControlServicePolicy, NodeCredential


__all__ = [
    "flocker_dataset_agent_main",
    "flocker_container_agent_main",
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


class _TLSContext(PRecord):
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
            }
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
class AgentScript(PRecord):
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


class AgentServiceFactory(PRecord):
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
    get_external_ip = field(initial=_get_external_ip, mandatory=True)

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


def _zfs_storagepool(
        reactor, pool=FLOCKER_POOL, mount_root=None, volume_config_path=None):
    """
    Create a ``VolumeService`` with a ``zfs.StoragePool``.

    :param pool: The name of the ZFS storage pool to use.
    :param bytes mount_root: The path to the directory where ZFS filesystems
        will be mounted.
    :param bytes volume_config_path: The path to the volume service's
        configuration file.

    :return: The ``VolumeService``, started.
    """
    if mount_root is None:
        mount_root = FLOCKER_MOUNTPOINT
    else:
        mount_root = FilePath(mount_root)
    if volume_config_path is None:
        config_path = DEFAULT_CONFIG_PATH
    else:
        config_path = FilePath(volume_config_path)

    pool = zfs.StoragePool(
        reactor=reactor, name=pool, mount_root=mount_root,
    )
    api = VolumeService(
        config_path=config_path,
        pool=pool,
        reactor=reactor,
    )
    api.startService()
    return api


class DeployerType(Names):
    """
    References to the different ``IDeployer`` implementations that are
    available.

    :ivar p2p: The "peer-to-peer" deployer - suitable for use with system like
        ZFS where nodes interact directly with each other for data movement.
    :ivar block: The Infrastructure-as-a-Service deployer - suitable for use
        with system like EBS where volumes can be attached to nodes as block
        devices and then detached (and then re-attached to other nodes).
    """
    p2p = NamedConstant()
    block = NamedConstant()


class BackendDescription(PRecord):
    """
    Represent one kind of storage backend we might be able to use.

    :ivar name: The human-meaningful name of this storage backend.
    :ivar needs_reactor: A flag which indicates whether this backend's API
        factory needs to have a reactor passed to it.
    :ivar needs_cluster_id: A flag which indicates whether this backend's API
        factory needs to have the cluster's unique identifier passed to it.
    :ivar api_factory: An object which can be called with some simple
        configuration data and which returns the API object implementing this
        storage backend.
    :ivar deployer_type: A constant from ``DeployerType`` indicating which kind
        of ``IDeployer`` the API object returned by ``api_factory`` is usable
        with.
    """
    name = field(type=unicode, mandatory=True)
    needs_reactor = field(type=bool, mandatory=True)
    # XXX Eventually everyone will take cluster_id so we will throw this flag
    # out.
    needs_cluster_id = field(type=bool, mandatory=True)
    api_factory = field(mandatory=True)
    deployer_type = field(
        mandatory=True,
        invariant=lambda value: (
            value in DeployerType.iterconstants(), "Unknown deployer_type"
        ),
    )

from .agents.cinder import cinder_from_configuration
from .agents.ebs import aws_from_configuration

# These structures should be created dynamically to handle plug-ins
_DEFAULT_BACKENDS = [
    # P2PManifestationDeployer doesn't currently know anything about
    # cluster_uuid.  It probably should so that it can make sure it
    # only talks to other nodes in the same cluster (maybe the
    # authentication layer would mostly handle this but maybe not if
    # you're slightly careless with credentials - also ZFS backend
    # doesn't use TLS yet).
    BackendDescription(
        name=u"zfs", needs_reactor=True, needs_cluster_id=False,
        api_factory=_zfs_storagepool, deployer_type=DeployerType.p2p,
    ),
    BackendDescription(
        name=u"loopback", needs_reactor=False, needs_cluster_id=False,
        # XXX compute_instance_id is the wrong type
        api_factory=LoopbackBlockDeviceAPI.from_path,
        deployer_type=DeployerType.block,
    ),
    BackendDescription(
        name=u"openstack", needs_reactor=False, needs_cluster_id=True,
        api_factory=cinder_from_configuration,
        deployer_type=DeployerType.block,
    ),
    BackendDescription(
        name=u"aws", needs_reactor=False, needs_cluster_id=True,
        api_factory=aws_from_configuration,
        deployer_type=DeployerType.block,
    ),
]

_DEFAULT_DEPLOYERS = {
    DeployerType.p2p: lambda api, **kw:
        P2PManifestationDeployer(volume_service=api, **kw),
    DeployerType.block: lambda api, **kw:
        BlockDeviceDeployer(block_device_api=ProcessLifetimeCache(api),
                            **kw),
}


class AgentService(PRecord):
    """
    :ivar backends: ``BackendDescription`` instances describing how to use each
        available storage backend.
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
        factory=pvector, initial=_DEFAULT_BACKENDS, mandatory=True,
    )
    deployers = field(factory=pmap, initial=_DEFAULT_DEPLOYERS, mandatory=True)
    reactor = field(initial=reactor, mandatory=True)

    get_external_ip = field(initial=_get_external_ip, mandatory=True)

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
        for backend in self.backends:
            if backend.name == self.backend_name:
                return backend
        try:
            return namedAny(self.backend_name + ".FLOCKER_BACKEND")
        except (AttributeError, ValueError):
            raise ValueError(
                "'{!s}' is neither a built-in backend nor a 3rd party "
                "module.".format(self.backend_name),
            )

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

        api_args = self.api_args
        if backend.needs_cluster_id:
            cluster_id = self.node_credential.cluster_uuid
            api_args = api_args.set("cluster_id", cluster_id)
        if backend.needs_reactor:
            api_args = api_args.set("reactor", self.reactor)

        return backend.api_factory(**api_args)

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
        )


class DatasetServiceFactory(PRecord):
    """
    A helper for creating most of the pieces that go into a dataset convergence
    agent.
    """
    agent_service_factory = field(initial=AgentService.from_configuration)
    configuration_factory = field(initial=get_configuration)

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
