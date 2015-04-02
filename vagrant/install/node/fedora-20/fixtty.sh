#!/bin/sh
# Fedora 20 default sudoers includes a line "Defaults requiretty", which
# prevents 'sudo' working from Vagrant provisioning scripts.  This script
# disables the line.

set -e

sed --in-place 's/^Defaults[ \t]*requiretty/# \0/' /etc/sudoers
