# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Run the control service benchmarks.
"""

from datetime import datetime
from functools import partial
import json
import os
from platform import node, platform
import sys
import yaml

from eliot import to_file

from twisted.internet.task import react
from twisted.python.usage import Options, UsageError

from flocker import __version__ as flocker_client_version

from benchmark._driver import driver

to_file(sys.stderr)


class BenchmarkOptions(Options):
    description = "Run benchmark tests."

    optParameters = [
        ['control', None, None,
         'IP address for a Flocker cluster control server.'],
        ['certs', None, 'certs',
         'Directory containing client certificates'],
        ['config', None, 'benchmark.yml',
         'YAML file describing benchmark options.'],
        ['scenario', None, 'default',
         'Environmental scenario under which to perform test.'],
        ['operation', None, 'default', 'Operation to measure.'],
        ['metric', None, 'default', 'Quantity to benchmark.'],
    ]


options = BenchmarkOptions()


def usage(message=None):
    sys.stderr.write(options.getUsage())
    sys.stderr.write('\n')
    sys.exit(message)

try:
    options.parseOptions()
except UsageError as e:
    usage(e.args[0])

if not options['control'] and options['operation'] != 'no-op':
    # No-op is OK with no control service
    usage('Control service required')

with open(options['config'], 'rt') as f:
    config = yaml.safe_load(f)
    scenarios = config['scenarios']
    operations = config['operations']
    metrics = config['metrics']

scenario_name = options['scenario']
operation_name = options['operation']
metric_name = options['metric']

scenario_config = scenarios.get(scenario_name) or usage(
    'No such scenario: {!r}'.format(scenario_name))
operation_config = operations.get(operation_name) or usage(
    'No such operation: {!r}'.format(operation_name))
metric_config = metrics.get(metric_name) or usage(
    'No such metric: {!r}'.format(metric_name))

timestamp = datetime.now().isoformat()

result = dict(
    timestamp=timestamp,
    client=dict(
        flocker_version=flocker_client_version,
        working_directory=os.getcwd(),
        username=os.environ[b"USER"],
        nodename=node(),
        platform=platform(),
    ),
    scenario=scenario_config.copy(),
    operation=operation_config.copy(),
    metric=metric_config.copy(),
)

react(
    driver, (
        options, scenario_config, operation_config, metric_config, result,
        partial(json.dump, fp=sys.stdout, indent=2)
    )
)
