# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Run the Flocker benchmarks.
"""

from datetime import datetime
from functools import partial
import json
import os
from platform import node, platform
import sys

from jsonschema import FormatChecker, Draft4Validator, ValidationError
import yaml

from eliot import to_file

from twisted.internet.task import react
from twisted.python.filepath import FilePath
from twisted.python.usage import Options, UsageError

from flocker import __version__ as flocker_client_version

from benchmark import metrics, operations, scenarios
from benchmark.cluster import BenchmarkCluster
from benchmark._driver import driver


to_file(sys.stderr)

# If modifying scenarios, operations, or metrics, please update
# docs/gettinginvolved/benchmarking.rst

_SCENARIOS = {
    'no-load': scenarios.NoLoadScenario,
    'read-request-load': scenarios.read_request_load_scenario,
    'write-request-load': scenarios.write_request_load_scenario,
}

_OPERATIONS = {
    'create-container': operations.CreateContainer,
    'create-dataset': operations.CreateDataset,
    'no-op': operations.NoOperation,
    'read-request': operations.ReadRequest,
    'wait': operations.Wait,
}

_METRICS = {
    'cputime': metrics.CPUTime,
    'wallclock': metrics.WallClock,
}


def create_factory_from_config(table, config):
    """
    Create a benchmark parameter factory from a configuration stanza.

    :param table: One of the scenario, operation, or metric tables
        mapping types to classes.
    :param config: The configuration stanza for the selected parameter.
    :return: A callable that just takes a Twisted reactor and cluster
        control service as  parameters to create the parameter instance.
    """
    args = config.copy()
    del args['name']
    key = args.pop('type')
    try:
        factory = table[key]
    except KeyError:
        return None
    return partial(factory, **args)


class BenchmarkOptions(Options):
    description = "Run benchmark tests."

    optParameters = [
        ['cluster', None, None,
         'Directory containing cluster configuration files.  '
         'If not set, use acceptance test environment variables.'],
        ['config', None, 'benchmark.yml',
         'YAML file describing benchmark options.'],
        ['samples', None, 3, 'Number of samples to take.'],
        ['scenario', None, 'default',
         'Environmental scenario under which to perform test.'],
        ['operation', None, 'default', 'Operation to measure.'],
        ['metric', None, 'default', 'Quantity to benchmark.'],
        ['userdata', None, None, 'JSON data to add to output.']
    ]


def usage(options, message=None):
    sys.stderr.write(options.getUsage())
    sys.stderr.write('\n')
    sys.exit(message)


def validate_configuration(configuration):
    """
    Validate a provided configuration.

    :param dict configuration: A desired configuration.
    :raises: jsonschema.ValidationError if the configuration is invalid.
    """
    schema = {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "type": "object",
        "required": ["scenarios", "operations", "metrics"],
        "properties": {
            "scenarios": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "required": ["name", "type"],
                    "properties": {
                        "name": {
                            "type": "string"
                        },
                        "type": {
                            "type": "string"
                        },
                    },
                    "additionalProperties": "true",
                },
            },
            "operations": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "required": ["name", "type"],
                    "properties": {
                        "name": {
                            "type": "string"
                        },
                        "type": {
                            "type": "string"
                        },
                    },
                    "additionalProperties": "true",
                },
            },
            "metrics": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "required": ["name", "type"],
                    "properties": {
                        "name": {
                            "type": "string"
                        },
                        "type": {
                            "type": "string"
                        },
                    },
                    "additionalProperties": "true",
                },
            }
        }
    }

    v = Draft4Validator(schema, format_checker=FormatChecker())
    v.validate(configuration)


def get_config_by_name(section, name):
    """
    Extract a named section from the configuration file
    """
    for config in section:
        if config['name'] == name:
            return config
    return None


def get_cluster(options, env):
    """
    Obtain a cluster from the command line options and environment.

    :param BenchmarkOption options: Parsed command line options.
    :param dict env: Dictionary of environment variables.
    :return BenchmarkCluster: Cluster to benchmark.
    """
    cluster_option = options['cluster']
    if cluster_option:
        try:
            cluster = BenchmarkCluster.from_cluster_yaml(
                FilePath(cluster_option)
            )
        except IOError as e:
            usage(
                options, 'Cluster file {!r} not found.'.format(e.filename)
            )
    else:
        try:
            cluster = BenchmarkCluster.from_acceptance_test_env(env)
        except KeyError as e:
            usage(
                options, 'Environment variable {!r} not set.'.format(e.args[0])
            )
        except ValueError as e:
            usage(options, e.args[0])
        except ValidationError as e:
            usage(options, e.message)
    return cluster


def parse_userdata(options):
    """
    Parse the userdata option and add to result.

    :param BenchmarkOptions options: Script options.
    :return: Parsed user data.
    """
    userdata = options['userdata']
    if userdata:
        try:
            if userdata.startswith('@'):
                try:
                    with open(userdata[1:]) as f:
                        return json.load(f)
                except IOError as e:
                    usage(
                        options,
                        'Invalid user data file: {}'.format(e.strerror)
                    )
            else:
                return json.loads(userdata)
        except ValueError as e:
            usage(options, 'Invalid user data: {}'.format(e.args[0]))
    return None


def main(argv, environ, react=react):
    options = BenchmarkOptions()

    try:
        options.parseOptions(argv[1:])
    except UsageError as e:
        usage(options, e.args[0])

    cluster = get_cluster(options, environ)

    with open(options['config'], 'rt') as f:
        config = yaml.safe_load(f)

    validate_configuration(config)

    scenario_name = options['scenario']
    scenario_config = get_config_by_name(config['scenarios'], scenario_name)
    if scenario_config is None:
        usage(options, 'Invalid scenario name: {!r}'.format(scenario_name))
    scenario_factory = create_factory_from_config(_SCENARIOS, scenario_config)
    if scenario_factory is None:
        usage(
            options,
            'Invalid scenario type: {!r}'.format(scenario_config['type'])
        )

    operation_name = options['operation']
    operation_config = get_config_by_name(config['operations'], operation_name)
    if operation_config is None:
        usage(options, 'Invalid operation name: {!r}'.format(operation_name))
    operation_factory = create_factory_from_config(
        _OPERATIONS, operation_config)
    if operation_factory is None:
        usage(
            options,
            'Invalid operation type: {!r}'.format(operation_config['type'])
        )

    metric_name = options['metric']
    metric_config = get_config_by_name(config['metrics'], metric_name)
    if metric_config is None:
        usage(options, 'Invalid metric name: {!r}'.format(metric_name))
    metric_factory = create_factory_from_config(_METRICS, metric_config)
    if metric_factory is None:
        usage(
            options, 'Invalid metric type: {!r}'.format(metric_config['type'])
        )

    try:
        num_samples = int(options['samples'])
    except ValueError:
        usage(options, 'Invalid sample count: {!r}'.format(options['samples']))

    timestamp = datetime.now().isoformat()

    result = dict(
        timestamp=timestamp,
        client=dict(
            flocker_version=flocker_client_version,
            working_directory=os.getcwd(),
            username=environ[b"USER"],
            nodename=node(),
            platform=platform(),
        ),
        scenario=scenario_config,
        operation=operation_config,
        metric=metric_config,
    )

    userdata = parse_userdata(options)
    if userdata:
        result['userdata'] = userdata

    react(
        driver, (
            cluster, scenario_factory, operation_factory, metric_factory,
            num_samples, result, partial(json.dump, fp=sys.stdout, indent=2)
        )
    )

if __name__ == '__main__':
    main(sys.argv, os.environ)
