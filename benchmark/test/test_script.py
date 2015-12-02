# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.

from jsonschema.exceptions import ValidationError

from twisted.trial.unittest import SynchronousTestCase

from benchmark.script import validate_configuration, get_config


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
        config = get_config(self.config['scenarios'], 'default')
        self.assertEqual(config['name'], 'default')

    def test_default_operation(self):
        """
        Extracts default operation.
        """
        config = get_config(self.config['operations'], 'default')
        self.assertEqual(config['name'], 'default')

    def test_default_metric(self):
        """
        Extracts default metric.
        """
        config = get_config(self.config['metrics'], 'default')
        self.assertEqual(config['name'], 'default')
