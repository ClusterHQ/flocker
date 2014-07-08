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
yum install -y rpm-devel rpmlint mock createrepo
yum install -y docker-io geard
yum install -y python-devel python-tox python-virtualenv python-pip
yum install -y python-cffi libffi-devel
# Flocker python dependencies
yum install -y \
	python-eliot \
	python-zope-interface \
	pytz \
	python-characteristic \
	python-twisted \
	PyYAML \
	python-treq \
	python-netifaces \
	python-ipaddr \
	python-nomenclature

# Install for downloading wheelhouse
yum install -y wget

systemctl enable docker
systemctl enable geard
