# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.

from jsonschema.exceptions import ValidationError

from twisted.trial.unittest import SynchronousTestCase

from benchmark.cluster import validate_cluster_configuration


class ValidationTests(SynchronousTestCase):
    """
    Tests for configuration file validation.
    """

    def setUp(self):
        self.config = {
            'cluster_name': 'cluster',
            'agent_nodes': [
                {'public': '52.26.168.213', 'private': '10.0.36.170'},
                {'public': '52.34.157.1', 'private': '10.0.84.25'}
            ],
            'control_node': 'ec.us-west-2.compute.amazonaws.com',
            'users': ['user'],
            'os': 'ubuntu',
            'private_key_path': '/home/osboxes/devel/flocker/hybrid-master',
            'agent_config': {
                'version': 1,
                'control-service': {
                    'hostname': 'ec.us-west-2.compute.amazonaws.com',
                    'port': 4524
                },
                'dataset': {
                    'region': 'us-west-2',
                    'backend': 'aws',
                    'secret_access_key': 'XXXXXX',
                    'zone': 'us-west-2a',
                    'access_key_id': 'AKIAXXXX'
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
        with self.assertRaises(ValidationError):
            validate_cluster_configuration(self.config)

    def test_missing_agent_nodes(self):
        """
        Rejects configuration with missing agent_nodes property.
        """
        del self.config['agent_nodes']
        with self.assertRaises(ValidationError):
            validate_cluster_configuration(self.config)
