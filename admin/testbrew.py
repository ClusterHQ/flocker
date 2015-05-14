#!/usr/bin/env python
# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Script to instantiate an OS X Virtual Machine to a snapshot with a clean
homebrew install, then executes via SSH the brew update, install and test
commands to verify a successful installation of a homebrew recipe.

The host machine must have:
        * A VMWare OS X VM available at a particular location

The guest virtual machine must have:
        * A snapshot with a particular name, homebrew-clean
        * Homebrew installed and available
"""

import os
import sys
import urllib2

from eliot import add_destination

from twisted.internet.defer import inlineCallbacks
from twisted.internet.error import ProcessTerminated
from twisted.python.filepath import FilePath
from twisted.python.usage import Options, UsageError

from flocker.provision._install import (
    task_test_homebrew,
    task_configure_brew_path,
)
from flocker.provision._ssh import run_remotely
from flocker.provision._ssh._conch import make_dispatcher
from flocker.provision._effect import sequence
from effect.twisted import perform
from flocker import __version__

from .runner import run

YOSEMITE_VMX_PATH = os.path.expanduser((
    "~/Documents/Virtual Machines.localized/"
    "OS X 10.10.vmwarevm/OS X 10.10.vmx"
))

YOSEMITE_SNAPSHOT = "homebrew-clean"

VM_USERNAME = "ClusterHQVM"

VM_HOST = "10.0.126.88"


class TestBrewOptions(Options):
    description = ("Start a VMWare OS X VM and test a brew recipe "
                   "installation.")

    optParameters = [
        ['vmhost', 'h', VM_HOST,
         'IP address or hostname of the Virtual Machine'],
        ['vmuser', 'u', VM_USERNAME,
         'Username for the Virtual Machine'],
        ['vmpath', 'p', YOSEMITE_VMX_PATH,
         'Full path to the Virtual Machine image'],
        ['vmsnapshot', 's', YOSEMITE_SNAPSHOT,
         'Snapshot identifier for the Virtual Machine'],
    ]

    synopsis = ('Usage: test-brew-recipe [options] <recipe URL>')

    def parseArgs(self, *args):
        if len(args) < 1:
            raise UsageError((
                "URL of homebrew recipe not specified. "
                "Run with --help for usage"
            ))
        else:
            self['recipe_url'] = args[0]

    def opt_version(self):
        """Print the program's version and exit."""
        sys.stdout.write(__version__.encode('utf-8') + b'\n')
        sys.exit(0)


MESSAGE_FORMATS = {
    "flocker.provision.ssh:run":
        "[%(username)s@%(address)s]: Running %(command)s\n",
    "flocker.provision.ssh:run:output":
        "[%(username)s@%(address)s]: %(line)s\n",
    "admin.runner:run":
        "Running %(command)s\n",
    "admin.runner:run:output":
        "%(line)s\n",
}


def eliot_output(message):
    """
    Write pretty versions of eliot log messages to stdout.
    """
    message_type = message.get('message_type', message.get('action_type'))
    sys.stdout.write(MESSAGE_FORMATS.get(message_type, '') % message)
    sys.stdout.flush()


@inlineCallbacks
def main(reactor, args, base_path, top_level):
    try:
        options = TestBrewOptions()
        try:
            options.parseOptions(args)
        except UsageError as e:
            sys.stderr.write("Error: {error}.\n".format(error=str(e)))
            sys.exit(1)

        add_destination(eliot_output)

        recipe_url = options['recipe_url']
        options['vmpath'] = FilePath(options['vmpath'])
        # Open the recipe URL just to validate and verify that it exists.
        # We do not need to read its content.
        urllib2.urlopen(recipe_url)
        yield run(reactor, [
            "vmrun", "revertToSnapshot",
            options['vmpath'].path, options['vmsnapshot'],
        ])
        yield run(reactor, [
            "vmrun", "start", options['vmpath'].path, "nogui",
        ])
        yield perform(
            make_dispatcher(reactor),
            run_remotely(
                username=options['vmuser'],
                address=options['vmhost'],
                commands=sequence([
                    task_configure_brew_path(),
                    task_test_homebrew(recipe_url),
                ]),
            ),
        )
        yield run(reactor, [
            "vmrun", "stop", options['vmpath'].path, "hard",
        ])
        print "Done."
    except ProcessTerminated as e:
        sys.stderr.write(
            (
                "Error: Command terminated with exit status {code}.\n"
            ).format(code=e.exitCode)
        )
        raise
