#!/bin/sh

# This script performs the steps to build the base flocker-tutorial box until
# the box must be rebooted.

set -e

yum update -y
# Install useful yum repos
yum install -y https://s3.amazonaws.com/archive.zfsonlinux.org/epel/zfs-release$(rpm -E %dist).noarch.rpm
yum install -y kernel-devel kernel dkms gcc
yum install -y epel-release

# Rebuild VirtualBox Additions
# TODO check if this is necessary in the dev box
/etc/init.d/vboxadd setup
