#!/bin/sh

# This script performs the steps to build the base flocker-dev box until the
# box must be rebooted.

set -e

yum update -y
# Install useful yum repos
yum install -y https://s3.amazonaws.com/archive.zfsonlinux.org/epel/zfs-release$(rpm -E %dist).noarch.rpm
yum install -y epel-release

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
	libffi-devel \
	yum-utils \
	pypy pypy-devel
