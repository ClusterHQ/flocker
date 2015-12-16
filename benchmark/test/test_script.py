# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.

from contextlib import contextmanager
from cStringIO import StringIO
import os
import shutil
import sys
import tempfile

from ipaddr import IPAddress
from jsonschema.exceptions import ValidationError

from twisted.trial.unittest import SynchronousTestCase

from benchmark.script import (
    BenchmarkOptions, get_cluster, validate_configuration, get_config_by_name
)


@contextmanager
def capture_stderr():
    """
    Context manager to capture stderr.

    Call the returned context variable to obtain captured output.
    """
    s = StringIO()
    out, sys.stderr = sys.stderr, s
    yield s.getvalue
    sys.stderr = out

# Addresses must be different, to check that environment is not used
# during YAML tests.
_ENV_CONTROL_SERVICE_ADDRESS = '10.0.0.1'
_YAML_CONTROL_SERVICE_ADDRESS = '10.1.0.1'

# Uses % formatting to prevent confusion with YAML braces.
_CLUSTER_YAML_CONTENTS = '''
control_node: %s
agent_nodes: []
''' % _YAML_CONTROL_SERVICE_ADDRESS


class ClusterConfigurationTests(SynchronousTestCase):
    """
    Tests for mapping cluster configuration to cluster.
    """

    def setUp(self):
        self.environ = {
            'FLOCKER_ACCEPTANCE_DEFAULT_VOLUME_SIZE': '107374182400',
            'FLOCKER_ACCEPTANCE_CONTROL_NODE': _ENV_CONTROL_SERVICE_ADDRESS,
            'FLOCKER_ACCEPTANCE_HOSTNAME_TO_PUBLIC_ADDRESS':
                '{"172.31.37.0": "52.11.208.0", "172.31.47.0": "52.32.250.0"}',
            'FLOCKER_ACCEPTANCE_VOLUME_BACKEND': 'aws',
            'FLOCKER_ACCEPTANCE_TEST_VOLUME_BACKEND_CONFIG':
                '/tmp/tmp84DVr3/dataset-backend.yml',
            'FLOCKER_ACCEPTANCE_NUM_AGENT_NODES': '2',
            'FLOCKER_ACCEPTANCE_API_CERTIFICATES_PATH': '/tmp/tmpSvE7ug',
        }

    def test_environment_setup_aws(self):
        """
        Uses environment variables for cluster configuration if option missing.

        This test checks a typical AWS configuration.
        """
        options = BenchmarkOptions()
        options.parseOptions([])
        cluster = get_cluster(options, self.environ)
        self.assertEqual(
            cluster.control_node_address(),
            IPAddress(_ENV_CONTROL_SERVICE_ADDRESS)
        )

    def test_environment_setup_rackspace(self):
        """
        Uses environment variables for cluster configuration if option missing.

        This test checks a typical Rackspace configuration.
        """
        self.environ['FLOCKER_ACCEPTANCE_HOSTNAME_TO_PUBLIC_ADDRESS'] = '{}'
        self.environ['FLOCKER_ACCEPTANCE_VOLUME_BACKEND'] = 'openstack'
        options = BenchmarkOptions()
        options.parseOptions([])
        cluster = get_cluster(options, self.environ)
        self.assertEqual(
            cluster.control_node_address(),
            IPAddress(_ENV_CONTROL_SERVICE_ADDRESS)
        )

    def test_yaml_setup(self):
        """
        Uses YAML file for cluster configuration if option given.

        This is true even if the environment contains a valid configuration.
        """
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir)
        with open(os.path.join(tmpdir, 'cluster.yml'), 'wt') as f:
            f.write(_CLUSTER_YAML_CONTENTS)
        options = BenchmarkOptions()
        options.parseOptions(['--cluster', tmpdir])
        cluster = get_cluster(options, self.environ)
        self.assertEqual(
            cluster.control_node_address(),
            IPAddress(_YAML_CONTROL_SERVICE_ADDRESS)
        )

    def test_missing_environment(self):
        """
        If no cluster option and no environment, script fails
        """
        options = BenchmarkOptions()
        options.parseOptions([])
        with capture_stderr() as captured_stderr:
            with self.assertRaises(SystemExit) as e:
                get_cluster(options, {})
            self.assertIn('not set', e.exception.args[0])
            self.assertIn(options.getUsage(), captured_stderr())

    def test_missing_yaml_file(self):
        """
        Script fails if cluster directory does not contain cluster.yml

        There is no fallback to environment if an error occurs reading
        YAML description.
        """
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir)
        options = BenchmarkOptions()
        options.parseOptions(['--cluster', tmpdir])
        with capture_stderr() as captured_stderr:
            with self.assertRaises(SystemExit) as e:
                get_cluster(options, self.environ)
            self.assertIn('not found', e.exception.args[0])
            self.assertIn(options.getUsage(), captured_stderr())

    def test_environment_invalid_control_node(self):
        """
        Rejects configuration if control node is invalid.
        """
        options = BenchmarkOptions()
        options.parseOptions([])
        self.environ['FLOCKER_ACCEPTANCE_CONTROL_NODE'] = 'notanipaddress'
        with capture_stderr() as captured_stderr:
            with self.assertRaises(SystemExit) as e:
                get_cluster(options, self.environ)
            self.assertIn('notanipaddress', e.exception.args[0])
            self.assertIn(options.getUsage(), captured_stderr())

    def test_environment_hostname_mapping_invalid_json(self):
        """
        Rejects configuration if hostname mapping is invalid.
        """
        options = BenchmarkOptions()
        options.parseOptions([])
        self.environ['FLOCKER_ACCEPTANCE_HOSTNAME_TO_PUBLIC_ADDRESS'] = '}'
        with capture_stderr() as captured_stderr:
            with self.assertRaises(SystemExit) as e:
                get_cluster(options, self.environ)
            self.assertIn('JSON', e.exception.args[0])
            self.assertIn(options.getUsage(), captured_stderr())

    def test_environment_hostname_mapping_not_object(self):
        """
        Rejects configuration if hostname mapping is invalid.
        """
        options = BenchmarkOptions()
        options.parseOptions([])
        self.environ['FLOCKER_ACCEPTANCE_HOSTNAME_TO_PUBLIC_ADDRESS'] = (
            '[{"notanipaddress": "notanipaddress"}]'
        )
        with capture_stderr() as captured_stderr:
            with self.assertRaises(SystemExit) as e:
                get_cluster(options, self.environ)
            self.assertIn('notanipaddress', e.exception.args[0])
            self.assertIn(options.getUsage(), captured_stderr())

    def test_environment_hostname_mapping_invalid_ipaddress(self):
        """
        Rejects configuration if hostname mapping is invalid.
        """
        options = BenchmarkOptions()
        options.parseOptions([])
        self.environ['FLOCKER_ACCEPTANCE_HOSTNAME_TO_PUBLIC_ADDRESS'] = (
            '{"notanipaddress": "notanipaddress"}'
        )
        with capture_stderr() as captured_stderr:
            with self.assertRaises(SystemExit) as e:
                get_cluster(options, self.environ)
            self.assertIn('notanipaddress', e.exception.args[0])
            self.assertIn(options.getUsage(), captured_stderr())

    def test_environment_invalid_volume_size(self):
        """
        Rejects configuration if volume size is invalid.
        """
        options = BenchmarkOptions()
        options.parseOptions([])
        self.environ['FLOCKER_ACCEPTANCE_DEFAULT_VOLUME_SIZE'] = 'A'
        with capture_stderr() as captured_stderr:
            with self.assertRaises(SystemExit) as e:
                get_cluster(options, self.environ)
            self.assertIn(
                'FLOCKER_ACCEPTANCE_DEFAULT_VOLUME_SIZE', e.exception.args[0]
            )
            self.assertIn(options.getUsage(), captured_stderr())


class ValidationTests(SynchronousTestCase):
    """
    Tests for configuration file validation.
    """

    def setUp(self):
        self.config = {
            'scenarios': [
                {
                    'name': 'default',
                    'type': 'no-load',
                }
            ],
            'operations': [
                {
                    'name': 'default',
                    'type': 'no-op',
                }
            ],
            'metrics': [
                {
                    'name': 'default',
                    'type': 'wallclock',
                }
            ]
        }

    def test_valid(self):
        """
        Accepts configuration file with valid entries.
        """
        validate_configuration(self.config)

    def test_config_extra_attribute(self):
        """
        Accepts configuration file with extra attributes.
        """
        self.config['extras'] = 3
        validate_configuration(self.config)

    def test_scenario_extra_attribute(self):
        """
        Accepts configuration file with extra attributes on scenario.
        """
        self.config['scenarios'][0]['extras'] = 3
        validate_configuration(self.config)

    def test_operation_extra_attribute(self):
        """
        Accepts configuration file with extra attributes on operations.
        """
        self.config['operations'][0]['extras'] = 3
        validate_configuration(self.config)

    def test_metric_extra_attribute(self):
        """
        Accepts configuration file with extra attributes on metrics.
        """
        self.config['metrics'][0]['extras'] = 3
        validate_configuration(self.config)

    def test_multiple_scenarios(self):
        """
        Accepts configuration file with multiple scenarios.
        """
        self.config['scenarios'].append({
            'name': 'another',
            'type': 'another'
        })
        validate_configuration(self.config)

    def test_multiple_operations(self):
        """
        Accepts configuration file with multiple operations.
        """
        self.config['operations'].append({
            'name': 'another',
            'type': 'another'
        })
        validate_configuration(self.config)

    def test_multiple_metrics(self):
        """
        Accepts configuration file with multiple metrics.
        """
        self.config['metrics'].append({
            'name': 'another',
            'type': 'another'
        })
        validate_configuration(self.config)

    def test_missing_scenarios(self):
        """
        Rejects configuration file with missing scenarios attribute.
        """
        del self.config['scenarios']
        with self.assertRaises(ValidationError):
            validate_configuration(self.config)

    def test_missing_operations(self):
        """
        Rejects configuration file with missing operations attribute.
        """
        del self.config['operations']
        with self.assertRaises(ValidationError):
            validate_configuration(self.config)

    def test_missing_metrics(self):
        """
        Rejects configuration file with missing metrics attribute.
        """
        del self.config['metrics']
        with self.assertRaises(ValidationError):
            validate_configuration(self.config)

    def test_empty_scenarios(self):
        """
        Rejects configuration file with empty scenarios attribute.
        """
        self.config['scenarios'] = {}
        with self.assertRaises(ValidationError):
            validate_configuration(self.config)

    def test_empty_operations(self):
        """
        Rejects configuration file with empty operations attribute.
        """
        self.config['operations'] = {}
        with self.assertRaises(ValidationError):
            validate_configuration(self.config)

    def test_empty_metrics(self):
        """
        Rejects configuration file with empty metrics attribute.
        """
        self.config['metrics'] = {}
        with self.assertRaises(ValidationError):
            validate_configuration(self.config)


class SubConfigurationTests(SynchronousTestCase):
    """
    Tests for getting sections from the configuration file.
    """

    def setUp(self):
        self.config = {
            'scenarios': [
                {
                    'name': 'default',
                    'type': 'no-load',
                }
            ],
            'operations': [
                {
                    'name': 'default',
                    'type': 'no-op',
                }
            ],
            'metrics': [
                {
                    'name': 'default',
                    'type': 'wallclock',
                }
            ]
        }

    def test_default_scenario(self):
        """
        Extracts default scenario.
        """
        config = get_config_by_name(self.config['scenarios'], 'default')
        self.assertEqual(config['name'], 'default')

    def test_default_operation(self):
        """
        Extracts default operation.
        """
        config = get_config_by_name(self.config['operations'], 'default')
        self.assertEqual(config['name'], 'default')

    def test_default_metric(self):
        """
        Extracts default metric.
        """
        config = get_config_by_name(self.config['metrics'], 'default')
        self.assertEqual(config['name'], 'default')
