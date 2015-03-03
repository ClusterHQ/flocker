#!/bin/sh

# This script builds the base flocker-dev box.

set -e

# Install useful yum repos
yum install -y http://archive.zfsonlinux.org/epel/zfs-release$(rpm -E %dist).noarch.rpm
yum install -y https://dl.fedoraproject.org/pub/epel/7/x86_64/e/epel-release-7-5.noarch.rpm

# Install packages
yum install -y \
	@buildsys-build git \
	dkms kernel-headers kernel-devel rpmdevtools \
	zlib-devel libuuid-devel libselinux-devel \
	automake autoconf libtool \
	rpm-devel rpmlint mock createrepo \
	docker \
	python-devel python-tox \
	python-virtualenv python-virtualenvwrapper python-pip \
	python-cffi libffi-devel \
	yum-utils \
	pypy pypy-devel

# Enable zfs-testing repo
yum-config-manager --enable zfs-testing
yum install -y zfs

systemctl enable docker

