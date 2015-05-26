#!/bin/sh

# This script performs the steps to build the base flocker-tutorial box until
# the box must be rebooted.

set -e

yum update -y

# Install a repository which has ZFS packages.
yum install -y https://s3.amazonaws.com/archive.zfsonlinux.org/epel/zfs-release$(rpm -E %dist).noarch.rpm

# Update the kernel and install some development tools necessary for building
# the ZFS kernel module.
yum install -y kernel-devel kernel dkms gcc make

# Install a repository that provides epel packages/updates.
yum install -y epel-release

# The kernel was just upgraded which means the existing VirtualBox Guest
# Additions will no longer work.  Build them again against the new version of
# the kernel.
/etc/init.d/vboxadd setup

# Create the 'docker' group (???)
groupadd docker
