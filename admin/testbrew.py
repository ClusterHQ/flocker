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
from subprocess import check_output, CalledProcessError

from twisted.python.filepath import FilePath
from twisted.python.usage import Options, UsageError

from flocker.provision._install import run_with_fabric, task_test_homebrew
from flocker import __version__


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


def main(args):
    try:
        options = TestBrewOptions()
        try:
            options.parseOptions(args)
        except UsageError as e:
            sys.stderr.write("Error: {error}.\n".format(error=str(e)))
            sys.exit(1)
        recipe_url = options['recipe_url']
        options['vmpath'] = FilePath(options['vmpath'])
        # Open the recipe URL just to validate and verify that it exists.
        # We do not need to read its content.
        urllib2.urlopen(recipe_url)
        check_output([
            "vmrun", "revertToSnapshot",
            options['vmpath'].path, options['vmsnapshot'],
        ])
        check_output([
            "vmrun", "start", options['vmpath'].path, "nogui",
        ])
        commands = task_test_homebrew(recipe_url)
        run_with_fabric(options['vmuser'], options['vmhost'],
                        commands=commands)
        check_output([
            "vmrun", "stop", options['vmpath'].path, "hard",
        ])
        print "Done."
    except CalledProcessError as e:
        sys.stderr.write(
            (
                "Error: Command {cmd} terminated with exit status {code}.\n"
            ).format(cmd=" ".join(e.cmd), code=e.returncode)
        )
        raise


if __name__ == "__main__":
    main(sys.argv[1:])
