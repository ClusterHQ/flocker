# Revert the Yosemite virtualmachine to a state where homebrew has
# just been installed, start the machine and ssh into it.

# PATH="${PATH}:/Applications/VMware Fusion.app/Contents/Library"
# YOSEMITE_VMX_PATH="${HOME}/Desktop/Virtual Machines.localized/OS X 10.10.vmwarevm/OS X 10.10.vmx"
#
# vmrun revertToSnapshot "${YOSEMITE_VMX_PATH}" homebrew-clean
# # vmrun start "${YOSEMITE_VMX_PATH}" nogui
# vmrun start "${YOSEMITE_VMX_PATH}"
# sleep 100
#
#
# # ssh -o ConnectTimeout=500 ClusterHQVM@172.18.140.54
# fab --timeout=200 -H ClusterHQVM@172.18.140.54 brew
#
# vmrun stop "${YOSEMITE_VMX_PATH}" hard

from vmfusion import vmrun
import os
from flocker.provision._install import run, Run


YOSEMITE_VMX_PATH = "{HOME}/Desktop/Virtual Machines.localized/OS X 10.10.vmwarevm/OS X 10.10.vmx".format(HOME=os.environ['HOME'])
VM_ADDRESS = "172.18.140.54"

vmrun.start(YOSEMITE_VMX_PATH, gui=True)
# from time import sleep
# sleep(50)

update = "brew update"
install = "brew install https://raw.githubusercontent.com/ClusterHQ/homebrew-tap/release/flocker-0.3.3dev6/flocker-0.3.3dev6.rb"
test = "brew test flocker-0.3.3dev6"

for command in [update, install, test]:
    run(username="ClusterHQVM", address=VM_ADDRESS, commands=[Run(command=command)])
