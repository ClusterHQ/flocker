"""
Check if a service is running
"""

# TODO: maybe check if it is enabled as well.

import os
import sys
from subprocess import check_output

service = sys.argv[1]

if os.path.exists("/etc/redhat-release"):
    # Redhat-based system:
    if "active (running)" not in \
       check_output(["systemctl", "status", service]):
        sys.exit(1)
else:
    if 'start/running' not in check_output(["service", service, "status"]):
        sys.exit(1)
