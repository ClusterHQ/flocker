#!/usr/bin/env python
# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Script executed by Buildbot on the Mac mini build slave, this instantiates the
OS X Virtual Machine to a snapshot with a clean homebrew install, then executes
via SSH the brew update, install and test commands to verify a successful
installation of a homebrew recipe.

The host machine must have:
        * A VMWare OS X VM available at a particular location

The guest virtual machine must have:
        * A snapshot with a particular name, homebrew-clean
        * Homebrew installed and available
"""

from _preamble import TOPLEVEL, BASEPATH

import os
import sys
import urllib2

from twisted.python.usage import Options, UsageError

from subprocess import check_output, CalledProcessError

from flocker.provision._install import run_with_fabric, task_test_homebrew


YOSEMITE_VMX_PATH = (
    '"'
    "{home}/Documents/Virtual Machines.localized/"
    "OS X 10.10.vmwarevm/OS X 10.10.vmx"
    '"'
).format(home=os.getenv("HOME"))

YOSEMITE_SNAPSHOT = "homebrew-clean"

VM_USERNAME = "ClusterHQVM"

VM_HOST = "10.0.126.88"


class TestBrewOptions(Options):
    description = ("Start a OS X Virtual Machine and test a brew recipe "
                   "installatiion.")

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

    synopsis = ('Usage: testbrew.py <recipe URL> [--vmhost <host>] '
                '[--vmuser <username>] '
                '[--vmpath <path>] '
                '[--vmsnapshot <name>]')

    def parseArgs(self, *args):
        if len(args) < 1:
            raise UsageError((
                "URL of homebrew recipe not specified. "
                "Run with --help for usage"
            ))
        else:
            self['recipe_url'] = args[0]


def main():
    try:
        # The following line is present just to prevent flake8 warnings.
        BASEPATH, TOPLEVEL
        options = TestBrewOptions()
        try:
            options.parseOptions()
        except UsageError as e:
            sys.stderr.write("Error: {error}.\n".format(error=str(e)))
            sys.exit(1)
        recipe_url = options['recipe_url']
        # Open the recipe URL just to validate and verify that it exists.
        # We do not need to read its content.
        urllib2.urlopen(recipe_url)
        check_output([
            "vmrun", "revertToSnapshot", YOSEMITE_VMX_PATH, YOSEMITE_SNAPSHOT,
        ])
        check_output([
            "vmrun", "start", YOSEMITE_VMX_PATH, "nogui",
        ])
        commands = task_test_homebrew(recipe_url)
        run_with_fabric(VM_USERNAME, VM_HOST,
                        commands=commands)
        check_output([
            "vmrun", "stop", YOSEMITE_VMX_PATH, "hard",
        ])
        print "Done."
        sys.exit(0)
    except CalledProcessError as e:
        sys.stderr.write(
            (
                "Error: Command {cmd} terminated with exit status {code}.\n"
            ).format(cmd=" ".join(e.cmd), code=e.returncode)
        )
        sys.exit(1)
    except Exception as e:
        sys.stderr.write("Error: {error}.\n".format(error=str(e)))
        sys.exit(1)

if __name__ == "__main__":
    main()
