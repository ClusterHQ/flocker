import sys

from eliot import to_file

from twisted.internet.task import react
from twisted.python.usage import Options, UsageError

from benchmark_driver import driver
from benchmark_scenarios import supported_scenarios, default_scenario
from benchmark_operations import supported_operations, default_operation
from benchmark_measurements import supported_measurements, default_measurement

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

react(
    driver, (
        config['control'], config['certs'], config['operation'],
        config['measure'], config['scenario']
    )
)
