# Copyright ClusterHQ Inc.  See LICENSE file for details.

import sys

from twisted.python.usage import Options, UsageError
from twisted.internet.defer import succeed

from pyrsistent import PClass

from zope.interface import implementer

from .diagnostics import list_hardware

from ..common.script import (
    ICommandLineScript,
    flocker_standard_options, FlockerScriptRunner)


class HardwareReportOptions(Options):
    """
    Command line options for ``flocker-benchmark hardware-report``.
    """
    longdesc = """\
    Print a hardware report.
    """


@flocker_standard_options
class BenchmarkOptions(Options):
    """
    Command line options for ``flocker-benchmark``.
    """
    longdesc = """\
    Tools for running Flocker benchmarks.
    """

    synopsis = "Usage: flocker-benchmark [OPTIONS]"

    subCommands = [
        ['hardware-report', None, HardwareReportOptions,
         "Print a hardware report."],
    ]

    def postOptions(self):
        if not self.subCommand:
            raise UsageError('Please supply subcommand name.')


def hardware_report(options):
    """
    Print a hardware report to stdout.
    """
    sys.stdout.write(
        list_hardware(['processor', 'memory', 'network', 'disk', 'volume'])
    )
    return succeed(None)


@implementer(ICommandLineScript)
class BenchmarkScript(PClass):
    """
    Implement top-level logic for the ``flocker-benchmark``.
    """
    _subcommands = {
        'hardware-report': hardware_report,
    }

    def main(self, reactor, options):
        subcommand = options.subCommand
        return self._subcommands[subcommand](options.subOptions)


def flocker_benchmark_main():
    return FlockerScriptRunner(
        script=BenchmarkScript(),
        options=BenchmarkOptions(),
        logging=False,
    ).main()
