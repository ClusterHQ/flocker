#!/bin/sh

# This script performs the steps to build the base flocker-tutorial box until
# the box must be rebooted.

set -e

yum update -y
# Install useful yum repos
yum install -y https://s3.amazonaws.com/archive.zfsonlinux.org/epel/zfs-release$(rpm -E %dist).noarch.rpm
yum install -y epel-release

yum install --enablerepo zfs-testing -y kernel-devel kernel dkms gcc

# Rebuild VirtualBox Additions
/etc/init.d/vboxadd setup
