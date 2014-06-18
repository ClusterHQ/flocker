# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Helpers for flocker shell commands."""

import sys

from twisted.internet.task import react
from twisted.python import usage

from .. import __version__


def flocker_standard_options(cls):
    """
    Add various standard command line options to flocker commands and
    subcommands.
    """
    original_init = cls.__init__

    def __init__(self, *args, **kwargs):
        self._sys_module = kwargs.pop('sys_module', sys)
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


class FlockerScriptRunner(object):
    """
    An API for running standard flocker scripts.
    """
    _react = staticmethod(react)

    def __init__(self, script, options, sys_module=None):
        """
        """
        self.script = script
        self.options = options

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
        try:
            self.options.parseOptions(arguments)
        except usage.UsageError as e:
            self.sys_module.stderr.write(unicode(self.options).encode('utf-8'))
            self.sys_module.stderr.write(
                b'ERROR: ' + e.message.encode('utf-8') + b'\n')
            raise SystemExit(1)
        return self.options

    def main(self):
        """
        Parse arguments and run the script's main function via L{react}.
        """
        options = self._parseOptions(self.sys_module.argv[1:])
        return self._react(self.script.main, (options,))
