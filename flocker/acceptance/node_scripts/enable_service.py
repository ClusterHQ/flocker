"""
Start a service and enable across reboots.
"""

import os
import sys
from subprocess import check_call, check_output

service = sys.argv[1]

if os.path.exists("/etc/redhat-release"):
    # Redhat-based system:
    check_call(["systemctl", "enable", service])
    check_call(["systemctl", "start", service])
else:
    # Ubuntu 14.04
    override = "/etc/init/%s.override" % (service,)
    if os.path.exists(override):
        os.remove(override)
    # `service <service-name> start` isn't idempotent.
    # `service <service-name> status` will display the status in a format that
    # looks like `<service-name> <goal>/<state>` possibly followed by a PID.
    # If the service is running, the goal will be `start` and the state will be
    # `running`.
    if 'start/running' not in check_output(["service", service, "status"]):
        check_call(["service", service, "start"])
