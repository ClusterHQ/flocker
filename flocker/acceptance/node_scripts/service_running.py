"""
Check if a service is running
"""

# TODO: maybe check if it is enabled as well.

import sys
from subprocess import check_output, CalledProcessError

service = sys.argv[1]

try:
    check_output(["systemctl", "--version"])
except CalledProcessError, OSError:
    systemd_system = False
else:
    systemd_system = True

if systemd_system:
    if "active (running)" not in \
       check_output(["systemctl", "status", service]):
        sys.exit(1)
else:
    if 'start/running' not in check_output(["service", service, "status"]):
        sys.exit(1)
