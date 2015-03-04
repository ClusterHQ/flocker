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

from subprocess import check_output, CalledProcessError

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
        # Open the recipe URL just to validate and verify that it exists.
        # We do not need to read its content.
        recipe_resource = urllib2.urlopen(recipe_url)
        revert_result = check_output([
            "vmrun", "revertToSnapshot", YOSEMITE_VMX_PATH, YOSEMITE_SNAPSHOT,
        ])
        start_result = check_output([
            "vmrun", "start", YOSEMITE_VMX_PATH, "nogui",
        ])
        run_with_fabric(VM_USERNAME, VM_HOST, commands=[
            Run(command="brew update"),
            Run(command="brew install {url}".format(url=recipe_url)),
            Run(command="brew test {url}".format(url=recipe_url)),
        ])
        stop_result = check_output([
            "vmrun", "stop", YOSEMITE_VMX_PATH, "hard",
        ])
        print "Done."
        sys.exit(0)
    except CalledProcessError as e:
        print (
            "Error: Command {cmd} terminated with exit status {code}.").format(
            cmd=" ".join(e.cmd), code=e.returncode
        )
        sys.exit(1)
    except Exception as e:
        print "Error: {error}.".format(error=str(e))
        sys.exit(1)

if __name__ == "__main__":
    main()
