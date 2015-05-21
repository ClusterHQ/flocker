# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_script,flocker.node.functional.test_script -*- # noqa

"""
The command-line ``flocker-*-agent`` tools.
"""

from socket import socket
from os import getpid

import yaml

from jsonschema import FormatChecker, Draft4Validator

from pyrsistent import PRecord, field, PMap, pmap

from zope.interface import implementer

from twisted.python.filepath import FilePath
from twisted.python.usage import Options
from twisted.internet.ssl import Certificate
from twisted.internet import reactor

from ..volume.service import (
    ICommandLineVolumeScript, VolumeScript,
)

from ..volume.script import flocker_volume_options
from ..volume.filesystems import zfs
from ..volume.service import VolumeService

from ..common.script import (
    ICommandLineScript,
    flocker_standard_options, FlockerScriptRunner, main_for_service)
from . import P2PManifestationDeployer, ApplicationNodeDeployer
from ._loop import AgentLoopService
from .agents.blockdevice import LoopbackBlockDeviceAPI, BlockDeviceDeployer
from ..ca import ControlServicePolicy, NodeCredential


__all__ = [
    "flocker_dataset_agent_main",
]


def _get_external_ip(host, port):
    """
    Get an external IP address for this node that can in theory connect to
    the given host and port.

    See https://clusterhq.atlassian.net/browse/FLOC-1751 for better solution.
    :param host: A host to connect to.
    :param port: The port to connect to.

    :return unicode: IP address of external interface on this node.
    """
    sock = socket()
    try:
        sock.setblocking(False)
        sock.connect_ex((host, port))
        return unicode(sock.getsockname()[0], "ascii")
    finally:
        sock.close()


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

    :param dict configuration: A desired configuration for an agent.

    :raises: jsonschema.ValidationError if the configuration is invalid.
    """
    # XXX Create a function which loads and validates, and also setting
    # defaults. FLOC-1925.
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
                "oneOf": [
                    {
                        "required": ["backend"],
                        "properties": {
                            "backend": {
                                "type": "string",
                                "pattern": "zfs",
                            },
                            "pool": {
                                "type": "string",
                            },
                        }
                    },
                    {
                        "required": ["backend"],
                        "properties": {
                            "backend": {
                                "type": "string",
                                "pattern": "loopback",
                            },
                            "pool": {
                                "type": "string",
                            },
                        }

                    },
                ]
            }
        }
    }

    v = Draft4Validator(schema, format_checker=FormatChecker())
    v.validate(configuration)


@flocker_standard_options
@flocker_volume_options
class _AgentOptions(Options):
    """
    Command line options for agents.
    """
    # Use as basis for subclass' synopsis:
    synopsis = "Usage: {} [OPTIONS]"

    optParameters = [
        ["agent-config", "c", "/etc/flocker/agent.yml",
         "The configuration file to set the control service."],
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
    XXX This is temporarily not used for the ``flocker-dataset-agent`` script.
    See FLOC-1924.

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
    """
    # This should have an explicit interface:
    # https://clusterhq.atlassian.net/browse/FLOC-1929
    deployer_factory = field(mandatory=True)

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
        agent_config = options[u'agent-config']
        configuration = yaml.safe_load(agent_config.getContent())

        validate_configuration(configuration=configuration)

        host = configuration['control-service']['hostname']
        port = configuration['control-service'].get('port', 4524)
        ip = _get_external_ip(host, port)
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


def flocker_dataset_agent_main():
    """
    Implementation of the ``flocker-dataset-agent`` command line script.

    This starts a dataset convergence agent.  It currently supports only the
    loopback block device backend.  Later it will be capable of starting a
    dataset agent using any of the supported dataset backends.
    """
    options = DatasetAgentOptions()

    return FlockerScriptRunner(
        script=NewAgentScript(),
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


def get_configuration(options):
    agent_config = options[u'agent-config']
    configuration = yaml.safe_load(agent_config.getContent())

    validate_configuration(configuration=configuration)

    path = agent_config.parent()
    # This is a hack; from_path should be more
    # flexible. https://clusterhq.atlassian.net/browse/FLOC-1865
    configuration['ca-certificate'] = Certificate.loadPEM(
        path.child(b"cluster.crt").getContent())
    configuration['node-credential'] = NodeCredential.from_path(path, b"node")

    return configuration


def _zfs_storagepool(reactor, name, mount_root, volume_config_path):
    pool = zfs.StoragePool(
        reactor=reactor, name=name, mount_root=FilePath(mount_root),
    )
    api = VolumeService(
        config_path=FilePath(volume_config_path),
        pool=pool,
        reactor=reactor,
    )
    api.startService()
    return api

# These structures should be created dynamically to handle plug-ins
default_backends = {
    # P2PManifestationDeployer doesn't current know anything about
    # cluster_uuid.  It probably should so that it can make sure it
    # only talks to other nodes in the same cluster (maybe the
    # authentication layer would mostly handle this but maybe not if
    # you're slightly careless with credentials - also ZFS backend
    # doesn't use TLS yet).

    # api_factory, ignored, needs_reactor, needs_cluster_id
    'zfs': (_zfs_storagepool, {}, True, False),
    'loopback': (LoopbackBlockDeviceAPI.from_path, {
        'root_path': b"/var/lib/flocker/loopback",
        'compute_instance_id': bytes(getpid()).decode('utf-8'),
    }, False)
    # 'openstack': (CinderBlockDeviceAPI.from_config, {
    #    XXX Eventually everyone will take cluster_id so we will throw this
    #    flag out.
    # 'cluster_id': True,
    #     })
}
default_deployers = {
    'zfs': lambda api, **kw:
        P2PManifestationDeployer(volume_service=api, **kw),
    'loopback': lambda api, **kw:
        BlockDeviceDeployer(block_device_api=api, **kw),
    # 'openstack': lambda ... BlockDeviceDeployer ...,
}


class AgentService(PRecord):
    backends = field(initial=default_backends, mandatory=True)
    deployers = field(initial=default_deployers, mandatory=True)
    reactor = field(initial=reactor, mandatory=True)

    get_external_ip = field(initial=_get_external_ip, mandatory=True)

    control_service_host = field(type=bytes, mandatory=True)
    control_service_port = field(type=int, mandatory=True)

    node_credential = field(type=NodeCredential, mandatory=True)
    # Cannot use type=Certificate; pyrsistent rejects classic classes.
    ca_certificate = field(mandatory=True)

    backend = field(type=unicode, mandatory=True)
    api_args = field(type=PMap, factory=pmap, mandatory=True)

    @classmethod
    def from_configuration(cls, configuration):
        host = configuration['control-service']['hostname']
        port = configuration['control-service'].get('port', 4524)

        node_credential = configuration['node-credential']
        ca_certificate = configuration['ca-certificate']

        api_args = configuration['dataset']
        backend = api_args.pop('backend')

        return cls(
            control_service_host=host,
            control_service_port=port,

            node_credential=node_credential,
            ca_certificate=ca_certificate,

            backend=backend.decode("ascii"),
            api_args=api_args,
        )

    def get_tls_context(self):
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
        (api_factory, _, needs_reactor, needs_cluster_id) = self.backends[
            self.backend
        ]

        api_args = self.api_args
        if needs_cluster_id:
            cluster_id = self.node_credential.cluster_uuid
            api_args = api_args.set("cluster_id", cluster_id)
        if needs_reactor:
            api_args = api_args.set("reactor", self.reactor)

        return api_factory(**api_args)

    def get_deployer(self, api):
        """
        Create an ``IDeployer`` provider suitable for the configured backend
        and this node.

        :return: The ``IDeployer`` provider.
        """
        deployer_factory = self.deployers[self.backend]

        hostname = self.get_external_ip(
            self.control_service_host, self.control_service_port,
        )
        node_uuid = self.node_credential.uuid
        return deployer_factory(
            api=api, hostname=hostname, node_uuid=node_uuid,
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


class NewAgentScript(PRecord):

    agent_service_factory = field(initial=AgentService.from_configuration)
    configuration_factory = field(initial=get_configuration)

    def main(self, reactor, options):

        configuration = self.configuration_factory(options)

        agent_service = self.agent_service_factory(configuration)
        agent_service = agent_service.set(reactor=reactor)

        api = agent_service.get_api()

        deployer = agent_service.get_deployer(api)

        loop_service = agent_service.get_loop_service(deployer)

        return main_for_service(
            reactor,
            loop_service
        )
