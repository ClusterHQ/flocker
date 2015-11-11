import sys

from eliot import to_file

from twisted.internet.task import react
from twisted.python.usage import Options, UsageError

from benchmark_driver import driver

to_file(sys.stderr)


class BenchmarkOptions(Options):
    description = "Run benchmark tests."

    optParameters = [
        ['control', None, None,
         'IP address for a Flocker cluster control server. '],
        ['certs', None, 'certs',
         'Directory containing client certificates'],
        ['scenario', None, 'no_load',
         'Environmental scenario under which to perform test.'],
        ['measure', None, 'wallclock', 'Quantity to benchmark.'],
        ['operation', None, 'read-request', 'Operation to measure.'],
    ]


config = BenchmarkOptions()
try:
    config.parseOptions()
except UsageError as e:
    sys.stderr.write(config.getUsage())
    sys.stderr.write('{}\n'.format(str(e)))
    sys.exit(1)

react(
    driver, (
        config['control'], config['certs'], config['operation'],
        config['measure'], config['scenario']
    )
)
