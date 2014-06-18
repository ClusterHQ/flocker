# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""The command-line ``flocker-volume`` tool."""

import sys

from twisted.python.usage import Options, UsageError
from twisted.python.filepath import FilePath
from twisted.internet.task import react
from twisted.internet.defer import succeed

from .service import VolumeService, CreateConfigurationError
from .. import __version__


def flocker_standard_options(cls):
    """
    Add various standard command line options to flocker commands and
    subcommands.
    """
    original_init = cls.__init__
    def __init__(self, *args, **kwargs):
        self._sys_module = kwargs.pop('sys_module', sys)
        self.stdout = kwargs.pop('stdout', sys.stdout)
        self.stderr = kwargs.pop('stderr', sys.stderr)
        self['verbosity'] = 0
        original_init(self, *args, **kwargs)
    cls.__init__ = __init__


    def opt_version(self):
        """
        Print the program's version and exit.
        """
        self._sys_module.stdout.write(__version__.encode('utf-8') + b'\n')
        raise SystemExit(0)
    cls.opt_version = opt_version


    def opt_verbose(self):
        """
        Increase the verbosity.
        """
        self['verbosity'] += 1
    cls.opt_verbose = opt_verbose
    cls.opt_v = opt_verbose

    return cls



@flocker_standard_options
class FlockerVolumeOptions(Options):
    """Command line options for ``flocker-volume`` volume management tool."""

    longdesc = """flocker-volume allows you to manage volumes, filesystems
    that can be attached to Docker containers.

    At the moment no functionality has been implemented.
    """
    synopsis = "Usage: flocker-volume [OPTIONS]"

    optParameters = [
        ["config", None, b"/etc/flocker/volume.json",
         "The path to the config file."],
    ]

    def postOptions(self):
        self["config"] = FilePath(self["config"])



class FlockerScriptRunner(object):
    """
    An API for running standard flocker scripts.
    """
    _react = staticmethod(react)

    def __init__(self, script, sys_module=None):
        """
        """
        self.script = script

        if sys_module is None:
            sys_module = sys
        self.sys_module = sys_module


    def _parseOptions(self, arguments):
        """
        Parse the options defined in the script's options class.

        L{UsageErrors} are caught and printed to I{stderr} and the script then
        exits.

        @param arguments: The command line arguments to be parsed.
        @rtype: L{Options}
        """
        options = self.script.options(
            stdout=self.sys_module.stdout,
            stderr=self.sys_module.stderr)
        try:
            options.parseOptions(arguments)
        except UsageError as e:
            self.sys_module.stderr.write(unicode(options).encode('utf-8'))
            self.sys_module.stderr.write(b'ERROR: ' + e.message.encode('utf-8') + b'\n')
            raise SystemExit(1)
        return options


    def main(self):
        """
        Parse arguments and run the script's main function via L{react}.
        """
        options = self._parseOptions(self.sys_module.argv[1:])
        args = (self.sys_module.stdout, self.sys_module.stderr, options)
        return self._react(self.script.main, args)



class VolumeScript(object):
    """
    A volume manager script.
    """
    options = FlockerVolumeOptions

    def main(self, reactor, stdout, stderr, options):
        """
        Run a volume management server configured according to the supplied
        options.
        """
        service = VolumeService(config_path=options["config"], pool=None)
        try:
            service.startService()
        except CreateConfigurationError as e:
            stderr.write(b"Writing config file %s failed: %s\n" % (
                options["config"].path, e))
            raise SystemExit(1)
        return succeed(None)


flocker_volume_main = FlockerScriptRunner(VolumeScript).main
