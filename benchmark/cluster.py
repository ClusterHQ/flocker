# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.

from functools import partial
from ipaddr import IPAddress
import json

from jsonschema import FormatChecker, Draft4Validator
import yaml

from twisted.python.filepath import FilePath

from flocker.apiclient import FlockerClient


def validate_host_mapping(host_mapping):
    """
    Validate a provided host mapping.

    :param dict host_mapping: The parsed JSON host mapping from the
    environment variable ``FLOCKER_ACCEPTANCE_HOSTNAME_TO_PUBLIC_ADDRESS``.
    :raises: jsonschema.ValidationError if the configuration is invalid.
    """
    schema = {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "type": "object",
        "additionalProperties": "true",
    }

    v = Draft4Validator(schema, format_checker=FormatChecker())
    v.validate(host_mapping)


def validate_cluster_configuration(cluster_config):
    """
    Validate a provided cluster configuration.

    :param dict cluster_config: The cluster configuration.
    :raises: jsonschema.ValidationError if the configuration is invalid.
    """
    schema = {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "type": "object",
        "required": ["control_node", "agent_nodes"],
        "properties": {
            "control_node": {
                "type": "string",
            },
            "agent_nodes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["public", "private"],
                    "properties": {
                        "public": {
                            "type": "string"
                        },
                        "private": {
                            "type": "string"
                        },
                    },
                },
            },
        },
        "additionalProperties": "true",
    }

    v = Draft4Validator(schema, format_checker=FormatChecker())
    v.validate(cluster_config)


class BenchmarkCluster(object):
    """
    Cluster for benchmark performance.

    :ivar IPAddress control_node_address: IP address for control service.
    :ivar control_service_factory: Callable taking a reactor parameter,
        and returning a IFlockerAPIV1Client.
    :ivar dict[IPAddress: IPAddress] public_addresses: mapping of
        internal cluster IP addresses to public IP addresses.
    :ivar Optional[int] default_volume_size: Size for volume creation.
    """

    def __init__(
        self, control_node_address, control_service_factory, public_addresses,
        default_volume_size,
    ):
        self._control_node_address = control_node_address
        self._control_service_factory = control_service_factory
        self._public_addresses = public_addresses
        self._default_volume_size = default_volume_size
        self._control_service = None

    @classmethod
    def from_acceptance_test_env(cls, env):
        """
        Create a cluster from acceptance test environment variables.

        See the Flocker documentation acceptance testing page for more details.

        :param dict env: Dictionary mapping acceptance test environment names
            to values.
        :return: A ``BenchmarkCluster`` instance.
        :raise KeyError: if expected environment variables do not exist.
        :raise ValueError: if environment variables are malformed.
        :raise jsonschema.ValidationError: if host mapping is not a valid
            format.
        """
        control_node_address = env['FLOCKER_ACCEPTANCE_CONTROL_NODE']
        certs = FilePath(env['FLOCKER_ACCEPTANCE_API_CERTIFICATES_PATH'])
        try:
            host_to_public = json.loads(
                env['FLOCKER_ACCEPTANCE_HOSTNAME_TO_PUBLIC_ADDRESS']
            )
            validate_host_mapping(host_to_public)
            public_addresses = {
                IPAddress(k): IPAddress(v) for k, v in host_to_public.items()
            }
        except ValueError as e:
            raise type(e)(
                ': '.join(
                    ('FLOCKER_ACCEPTANCE_HOSTNAME_TO_PUBLIC_ADDRESS',) + e.args
                )
            )
        control_service = partial(
            FlockerClient,
            host=control_node_address,
            port=4523,
            ca_cluster_path=certs.child('cluster.crt'),
            cert_path=certs.child('user.crt'),
            key_path=certs.child('user.key')
        )
        try:
            control_node_ip = IPAddress(control_node_address)
        except ValueError as e:
            raise type(e)(
                ': '.join(('FLOCKER_ACCEPTANCE_CONTROL_NODE',) + e.args)
            )

        try:
            default_volume_size = int(
                env['FLOCKER_ACCEPTANCE_DEFAULT_VOLUME_SIZE']
            )
        except ValueError as e:
            raise type(e)(
                ': '.join(('FLOCKER_ACCEPTANCE_DEFAULT_VOLUME_SIZE',) + e.args)
            )

        return cls(
            control_node_ip, control_service, public_addresses,
            default_volume_size,
        )

    @classmethod
    def from_cluster_yaml(cls, path):
        """
        Create a cluster from Quick Start Installer files.

        :param FilePath path: directory containing Quick Start Installer
            ``cluster.yml`` and certificate files.
        :return: A ``BenchmarkCluster`` instance.
        """
        with path.child('cluster.yml').open() as f:
            cluster = yaml.safe_load(f)
        validate_cluster_configuration(cluster)
        control_node_address = cluster['control_node']
        public_addresses = {
            IPAddress(node['private']): IPAddress(node['public'])
            for node in cluster['agent_nodes']
        }
        control_service = partial(
            FlockerClient,
            host=control_node_address,
            port=4523,
            ca_cluster_path=path.child('cluster.crt'),
            cert_path=path.child('user.crt'),
            key_path=path.child('user.key')
        )
        return cls(
            IPAddress(control_node_address), control_service, public_addresses,
            None,
        )

    def control_node_address(self):
        """
        Return the control node IP address.
        """
        return self._control_node_address

    def get_control_service(self, reactor):
        """
        Return a provider of the ``IFlockerAPIV1Client`` interface.
        """
        control_service = self._control_service
        if control_service is None:
            control_service = self._control_service_factory(reactor)
            self._control_service = control_service
        return control_service

    def public_address(self, hostname):
        """
        Convert a node's internal hostname to a public address.  If the
        hostname does not exist in ``_public_addresses``, just return the
        hostname, and hope it is public.

        :param IPAddress hostname: Hostname for Flocker node.
        :return IPAddress: Public IP address for node.
        """
        return self._public_addresses.get(hostname, hostname)

    def default_volume_size(self):
        """
        Return the cluster default volume size.
        """
        return self._default_volume_size
