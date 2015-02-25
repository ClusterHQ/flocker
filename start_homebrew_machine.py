"""
Revert the Yosemite virtualmachine to a state where homebrew has just been
installed, start the machine and ssh into it. Then start a VM and test a
Homebrew script in that VM.

The machine must have:
    * VMWare Fusion installed,
    * A VMWare OS X VM available at a particular location

The VM must have:
    * A snapshot with a particular name,
    * Homebrew installed and available
"""

# TODO add vmfusion to setup.py and google doc
from vmfusion import vmrun
import os
from flocker.provision._install import run, Run


YOSEMITE_VMX_PATH = "{HOME}/Desktop/Virtual Machines.localized/OS X 10.10.vmwarevm/OS X 10.10.vmx".format(HOME=os.environ['HOME'])
VM_ADDRESS = "172.18.140.54"

# XXX Requires https://github.com/msteinhoff/vmfusion-python/pull/4 to be
# merged
vmrun.revertToSnapshot(YOSEMITE_VMX_PATH, 'homebrew-clean')
vmrun.start(YOSEMITE_VMX_PATH, gui=True)

version = "0.3.3dev6"
url = "https://raw.githubusercontent.com/ClusterHQ/homebrew-tap/release/flocker-{version}/flocker-{version}.rb".format(version=version)
update = "brew update"
install = "brew install " + url
test = "brew test flocker-{version}".format(version=version)

for command in [update, install, test]:
    run(username="ClusterHQVM", address=VM_ADDRESS, commands=[Run(command=command)])

vmrun.stop(YOSEMITE_VMX_PATH, soft=False)
