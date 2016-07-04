"""
Stop a service and disable across reboots.
"""

import sys
from subprocess import check_call, check_output, CalledProcessError

service = sys.argv[1]

try:
    check_output(["systemctl", "--version"])
except (CalledProcessError, OSError):
    systemd_system = False
else:
    systemd_system = True

if systemd_system:
    check_call(["systemctl", "disable", service])
    check_call(["systemctl", "stop", service])
else:
    # Ubuntu 14.04
    override = "/etc/init/%s.override" % (service,)
    with file(override, "w") as f:
        f.write("manual\n")
    if 'stop/waiting' not in check_output(["service", service, "status"]):
        check_call(["service", service, "stop"])
