#!/bin/sh

# This script builds the base flocker-dev box.

set -e

# Make it possible to install flocker-node
yum install -y https://s3.amazonaws.com/archive.zfsonlinux.org/fedora/zfs-release$(rpm -E %dist).noarch.rpm
yum install -y https://storage.googleapis.com/archive.clusterhq.com/fedora/clusterhq-release$(rpm -E %dist).noarch.rpm
yum install -y flocker-node-0.1.2

systemctl enable docker
systemctl enable geard

# Make it easy to authenticate as root
mkdir -p /root/.ssh
cp ~vagrant/.ssh/authorized_keys /root/.ssh

# Create a ZFS storage pool backed by a normal filesystem file.  This
# is a bad way to configure ZFS for production use but it is
# convenient for a demo in a VM.
mkdir -p /opt/flocker
truncate --size 1G /opt/flocker/pool-vdev
zpool create flocker /opt/flocker/pool-vdev
