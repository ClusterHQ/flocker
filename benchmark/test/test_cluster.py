# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.

from ipaddr import IPAddress
from uuid import uuid4

from jsonschema.exceptions import ValidationError

from twisted.internet.task import Clock

from flocker.apiclient import FakeFlockerClient, Node
from flocker.testtools import TestCase

from benchmark.cluster import BenchmarkCluster, validate_cluster_configuration


class ValidationTests(TestCase):
    """
    Tests for configuration file validation.
    """

    def setUp(self):
        super(TestCase, self).setUp()
        self.config = {
            'cluster_name': 'cluster',
            'agent_nodes': [
                {'public': '52.26.168.0', 'private': '10.0.36.0'},
                {'public': '52.34.157.0', 'private': '10.0.84.0'}
            ],
            'control_node': 'ec.region1.compute.amazonaws.com',
            'users': ['user'],
            'os': 'ubuntu',
            'private_key_path': '/home/example/private_key',
            'agent_config': {
                'version': 1,
                'control-service': {
                    'hostname': 'ec.region1.compute.amazonaws.com',
                    'port': 4524
                },
                'dataset': {
                    'region': 'region1',
                    'backend': 'aws',
                    'secret_access_key': 'secret',
                    'zone': 'region1a',
                    'access_key_id': 'AKIAsecret'
                }
            },
        }

    def test_valid(self):
        """
        Accepts configuration file with valid entries.
        """
        validate_cluster_configuration(self.config)

    def test_config_extra_attribute(self):
        """
        Accepts configuration file with empty agent node mapping.
        """
        self.config['agent_nodes'] = []
        validate_cluster_configuration(self.config)

    def test_missing_control_node(self):
        """
        Rejects configuration with missing control_node property.
        """
        del self.config['control_node']
        self.assertRaises(
            ValidationError,
            validate_cluster_configuration, self.config,
        )

    def test_missing_agent_nodes(self):
        """
        Rejects configuration with missing agent_nodes property.
        """
        del self.config['agent_nodes']
        self.assertRaises(
            ValidationError,
            validate_cluster_configuration, self.config,
        )


CONTROL_SERVICE_PUBLIC_IP = IPAddress('10.0.0.1')
CONTROL_SERVICE_PRIVATE_IP = IPAddress('10.1.0.1')

DEFAULT_VOLUME_SIZE = 1073741824


class BenchmarkClusterTests(TestCase):

    def setUp(self):
        super(BenchmarkClusterTests, self).setUp()
        node = Node(
            # Node public_address is actually the internal cluster address
            uuid=uuid4(), public_address=CONTROL_SERVICE_PRIVATE_IP
        )
        self.control_service = FakeFlockerClient([node])
        self.cluster = BenchmarkCluster(
            CONTROL_SERVICE_PUBLIC_IP,
            lambda reactor: self.control_service,
            {
                CONTROL_SERVICE_PRIVATE_IP: CONTROL_SERVICE_PUBLIC_IP,
            },
            DEFAULT_VOLUME_SIZE,
        )

    def test_control_node_address(self):
        """
        The ``control_node_address`` method gives expected results.
        """
        self.assertEqual(
            self.cluster.control_node_address(), CONTROL_SERVICE_PUBLIC_IP)

    def test_control_service(self):
        """
        The ``control_service`` method gives expected results.
        """
        self.assertIs(
            self.cluster.get_control_service(Clock()), self.control_service)

    def test_public_address(self):
        """
        The ``public_address`` method gives expected results.
        """
        self.assertEqual(
            self.cluster.public_address(CONTROL_SERVICE_PRIVATE_IP),
            CONTROL_SERVICE_PUBLIC_IP
        )

    def test_default_volume_size(self):
        """
        The ``default_volume_size`` method gives expected results.
        """
        self.assertEqual(
            self.cluster.default_volume_size(), DEFAULT_VOLUME_SIZE)
