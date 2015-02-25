#!/bin/sh

# This script builds the base flocker-dev box.

set -e

# Install useful yum repos
yum install -y https://s3.amazonaws.com/archive.zfsonlinux.org/fedora/zfs-release$(rpm -E %dist).noarch.rpm
curl https://copr.fedoraproject.org/coprs/tomprince/hybridlogic/repo/fedora-20-x86_64/tomprince-hybridlogic-fedora-20-x86_64.repo >/etc/yum.repos.d/hybridlogic.repo

# Install packages
yum install -y \
	@buildsys-build git \
	kernel-headers kernel-devel rpmdevtools \
	zlib-devel libuuid-devel libselinux-devel \
	automake autoconf libtool \
	rpm-devel rpmlint mock createrepo \
	docker-io \
	python-devel python-tox \
	python-virtualenv python-virtualenvwrapper python-pip \
	python-cffi libffi-devel \
	yum-utils \
	pypy pypy-devel

# Enable zfs-testing repo
yum-config-manager --enable zfs-testing
yum install -y zfs

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
# These are redundant with python-twisted
yum install -y \
	python-crypto \
	python-pyasn1
yum install -y python-flake8 python-coverage

# Install for downloading wheelhouse
yum install -y wget

systemctl enable docker

