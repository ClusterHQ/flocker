#!/bin/sh

set -e -x

UNAME_R=$(uname -r)
PV=${UNAME_R%.*}
KV=${PV%%-*}
SV=${PV##*-}
ARCH=$(uname -m)
sudo yum install -y https://kojipkgs.fedoraproject.org/packages/kernel/${KV}/${SV}/${ARCH}/kernel-devel-${UNAME_R}.rpm

sudo yum install -y https://s3.amazonaws.com/archive.zfsonlinux.org/fedora/zfs-release$(rpm -E %dist).noarch.rpm
sudo yum install -y https://s3.amazonaws.com/clusterhq-archive/fedora/clusterhq-release$(rpm -E %dist).noarch.rpm
sudo yum install -y --enablerepo=clusterhq-testing clusterhq-flocker-node

sudo systemctl enable docker.service
sudo systemctl start docker.service

sudo mkdir -p /var/opt/flocker
sudo truncate --size 10G /var/opt/flocker/pool-vdev
sudo zpool create flocker /var/opt/flocker/pool-vdev

/opt/flocker/bin/trial flocker
