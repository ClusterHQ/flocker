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


# If modifying scenarios, operations, or metrics, please update
# docs/gettinginvolved/benchmarking.rst

_SCENARIOS = {
    'no-load': scenarios.NoLoadScenario,
}

_DEFAULT_SCENARIO = 'no-load'

_OPERATIONS = {
    'no-op': operations.NoOperation,
    'read-request': operations.ReadRequest,
    'wait-10': operations.Wait,
}

_DEFAULT_OPERATION = 'read-request'

_METRICS = {
    'wallclock': metrics.WallClock,
}

_DEFAULT_METRIC = 'wallclock'


class BenchmarkOptions(Options):
    description = "Run benchmark tests."

    optParameters = [
        ['control', None, None,
         'IP address for a Flocker cluster control server.'],
        ['certs', None, 'certs',
         'Directory containing client certificates'],
        ['scenario', None, _DEFAULT_SCENARIO,
         'Environmental scenario under which to perform test. '
         'Supported values: {}.'.format(', '.join(_SCENARIOS))],
        ['operation', None, _DEFAULT_OPERATION,
         'Operation to measure. '
         'Supported values: {}.'.format(', '.join(_OPERATIONS))],
        ['metric', None, _DEFAULT_METRIC,
         'Quantity to benchmark. '
         'Supported values: {}.'.format(', '.join(_METRICS))],
    ]


config = BenchmarkOptions()
try:
    config.parseOptions()
    if not config['control'] and config['operation'] != 'no-op':
        # No-op is OK with no control service
        raise UsageError('Control service required')
except UsageError as e:
    sys.stderr.write(config.getUsage())
    sys.stderr.write('\n{}\n'.format(str(e)))
    sys.exit(1)


scenario = _SCENARIOS[config['scenario']]
operation = _OPERATIONS[config['operation']]
metric = _METRICS[config['metric']]

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
    scenario=config['scenario'],
    operation=config['operation'],
    metric=config['metric'],
)

react(
    driver, (
        config, scenario, operation, metric, result,
        partial(json.dump, fp=sys.stdout, indent=2)
    )
)
