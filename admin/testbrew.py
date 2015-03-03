#!/usr/bin/env python
# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Script executed by Buildbot on the Mac mini build slave, this instantiates the
OS X Virtual Machine to a snapshot with a clean homebrew install, then executes
via SSH the brew update, install and test commands to verify a successful
installation of a homebrew recipe.

The host machine must have:
        * VMWare Fusion installed,
        * A VMWare OS X VM available at a particular location

The guest virtual machine must have:
        * A snapshot with a particular name, homebrew-clean
        * Homebrew installed and available
"""

import os
import sys
import urllib2

from subprocess import check_output

from flocker.common._ssh import run_with_fabric, Run


YOSEMITE_VMX_PATH = (
    '"'
    "{home}/Documents/Virtual Machines.localized/"
    "OS X 10.10.vmwarevm/OS X 10.10.vmx"
    '"'
).format(home=os.getenv("HOME"))

YOSEMITE_SNAPSHOT = "homebrew-clean"

VM_USERNAME = "ClusterHQVM"

VM_HOST = "10.0.126.88"


def main():
    try:
        if len(sys.argv) < 2:
            raise Exception("URL of homebrew recipe not specified")
        recipe_url = sys.argv[1]
        # recipe_resource = urllib2.urlopen(recipe_url)
        # recipe = recipe_resource.read()
        revert_result = check_output([
            "vmrun", "revertToSnapshot", YOSEMITE_VMX_PATH, YOSEMITE_SNAPSHOT,
        ])
        start_result = check_output([
            "vmrun", "start", YOSEMITE_VMX_PATH, "nogui",
        ])
        run_with_fabric(VM_USERNAME, VM_HOST, commands=[
            Run(command="export GEBLER=\"Dave Gebler\"")
        ])
        print "Done."
        sys.exit(0)
    except Exception as e:
        print "Error: {error}.".format(error=str(e))
        sys.exit(1)

if __name__ == "__main__":
    main()
