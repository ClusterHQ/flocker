#!/bin/sh

# This script performs the steps to build the base flocker-dev box after the
# box has been rebooted. Installing ZFS requires a recent kernel.

set -e

# Enable zfs-testing repo
yum-config-manager --enable zfs-testing
yum install -y zfs

systemctl enable docker
