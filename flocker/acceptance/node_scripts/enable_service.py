"""
Start a service and enable across reboots.
"""

import os
import sys
from subprocess import check_call

service = sys.argv[1]

if os.path.exists("/etc/redhat-release"):
    # Redhat-based system:
    check_call(["systemctl", "enable", service])
    check_call(["systemctl", "start", service])
else:
    # Ubuntu 14.04
    override = "/etc/init/%.override" % (service,)
    if os.path.exists(override):
        os.remove(override)
    check_call(["service", service, "start"])
