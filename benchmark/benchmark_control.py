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

from eliot import to_file

from twisted.internet.task import react
from twisted.python.usage import Options, UsageError

from flocker import __version__ as flocker_client_version

from benchmark._driver import driver
from benchmark import metrics, operations, scenarios

to_file(sys.stderr)


_scenarios = {
    'no-load': scenarios.NoLoadScenario,
}

default_scenario = 'no-load'

_operations = {
    'no-op': operations.NoOperation,
    'read-request': operations.ReadRequest,
}

default_operation = 'read-request'

_metrics = {
    'wallclock': metrics.WallClock,
}

default_metric = 'wallclock'


class BenchmarkOptions(Options):
    description = "Run benchmark tests."

    optParameters = [
        ['control', None, None,
         'IP address for a Flocker cluster control server.'],
        ['certs', None, 'certs',
         'Directory containing client certificates'],
        ['scenario', None, default_scenario,
         'Environmental scenario under which to perform test. '
         'Supported values: {}.'.format(', '.join(_scenarios))],
        ['operation', None, default_operation,
         'Operation to measure. '
         'Supported values: {}.'.format(', '.join(_operations))],
        ['metric', None, default_metric,
         'Quantity to benchmark. '
         'Supported values: {}.'.format(', '.join(_metrics))],
    ]


config = BenchmarkOptions()
try:
    config.parseOptions()
except UsageError as e:
    sys.stderr.write(config.getUsage())
    sys.stderr.write('\n{}\n'.format(str(e)))
    sys.exit(1)


operation = _operations[config['operation']]
metric = _metrics[config['metric']]
scenario = _scenarios[config['scenario']]

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
    metric=config['metric'],
    operation=config['operation'],
    scenario=config['scenario'],
)

react(
    driver, (
        config, operation, metric, scenario, result,
        partial(json.dump, fp=sys.stdout, indent=2)
    )
)
