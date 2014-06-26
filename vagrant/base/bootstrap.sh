#!/bin/sh

# This script builds the base flocker-dev box.

set -e

# Install useful yum repos
yum localinstall -y http://archive.zfsonlinux.org/fedora/zfs-release$(rpm -E %dist).noarch.rpm
curl https://copr.fedoraproject.org/coprs/tomprince/hybridlogic/repo/fedora-20-x86_64/tomprince-hybridlogic-fedora-20-x86_64.repo >/etc/yum.repos.d/hybridlogic.repo

# Install packages
# Note zfs isn't installed due to license incompatibility
yum install -y @buildsys-build git
yum install -y kernel-headers kernel-devel rpmdevtools
yum install -y zlib-devel libuuid-devel libselinux-devel
yum install -y automake autoconf libtool
yum install -y rpm-devel rpmlint mock
yum install -y docker-io geard
yum install -y python-devel python-tox python-virtualenv python-pip
yum install -y createrepo
yum install -y python-twisted python-characteristic python-eliot pytz python-ipaddr
yum install -y python-cffi python-netifaces python-treq
yum install -y python-nomenclature

# Cleanup
rm -rf /tmp/* /var/tmp/*
dd if=/dev/zero of=/EMPTY bs=1M || true
rm -f /EMPTY
