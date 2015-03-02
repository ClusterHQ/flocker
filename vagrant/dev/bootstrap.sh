#!/bin/sh

# This script builds the base flocker-dev box.

set -e

# Install useful yum repos
yum install -y https://s3.amazonaws.com/archive.zfsonlinux.org/fedora/zfs-release$(rpm -E %dist).noarch.rpm

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

# Install for downloading wheelhouse
yum install -y wget

systemctl enable docker

