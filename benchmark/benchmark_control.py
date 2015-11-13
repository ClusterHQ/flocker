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
from benchmark._scenarios import (
    supported_scenarios, default_scenario, get_scenario)
from benchmark._operations import (
    supported_operations, default_operation, get_operation)
from benchmark._measurements import (
    supported_measurements, default_measurement, get_measurement)

to_file(sys.stderr)


class BenchmarkOptions(Options):
    description = "Run benchmark tests."

    optParameters = [
        ['control', None, None,
         'IP address for a Flocker cluster control server.'],
        ['certs', None, 'certs',
         'Directory containing client certificates'],
        ['scenario', None, default_scenario,
         'Environmental scenario under which to perform test. '
         'Supported values: {}.'.format(', '.join(supported_scenarios))],
        ['operation', None, default_operation,
         'Operation to measure. '
         'Supported values: {}.'.format(', '.join(supported_operations))],
        ['measure', None, default_measurement,
         'Quantity to benchmark. '
         'Supported values: {}.'.format(', '.join(supported_measurements))],
    ]


config = BenchmarkOptions()
try:
    config.parseOptions()
except UsageError as e:
    sys.stderr.write(config.getUsage())
    sys.stderr.write('\n{}\n'.format(str(e)))
    sys.exit(1)


operation = get_operation(name=config['operation'])
measurement = get_measurement(name=config['measure'])
scenario = get_scenario(name=config['scenario'])

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
    measurement=config['measure'],
    operation=config['operation'],
    scenario=config['scenario'],
)

react(
    driver, (
        config, operation, measurement, scenario, result,
        partial(json.dump, fp=sys.stdout, indent=2)
    )
)
