#!/bin/sh

# This script performs the steps to build the base flocker-dev box until the
# box must be rebooted.

set -e

yum update -y
# Install useful yum repos
yum install -y https://s3.amazonaws.com/archive.zfsonlinux.org/epel/zfs-release$(rpm -E %dist).noarch.rpm
yum install -y epel-release
yum install -y https://s3.amazonaws.com/clusterhq-archive/centos/clusterhq-release$(rpm -E %dist).noarch.rpm

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
	enchant \
	libffi-devel openssl-devel \
	yum-utils \
	pypy pypy-devel


# dpkg isn't currently available upstream
# https://bugzilla.redhat.com/show_bug.cgi?id=1149590
yum install -y \
	https://copr-be.cloud.fedoraproject.org/results/xaeth/dpkg/epel-7-x86_64/dpkg-1.16.15-2.fc22/dpkg-1.16.15-2.el7.centos.x86_64.rpm \
	https://copr-be.cloud.fedoraproject.org/results/xaeth/dpkg/epel-7-x86_64/dpkg-1.16.15-2.fc22/dpkg-dev-1.16.15-2.el7.centos.noarch.rpm
	https://copr-be.cloud.fedoraproject.org/results/xaeth/dpkg/epel-7-x86_64/dpkg-1.16.15-2.fc22/dpkg-perl-1.16.15-2.el7.centos.noarch.rpm
