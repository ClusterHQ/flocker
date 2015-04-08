#!/bin/sh

set -e -x

sudo yum install -y epel-release
sudo yum install -y https://s3.amazonaws.com/archive.zfsonlinux.org/epel/zfs-release.el7.noarch.rpm
sudo yum install -y https://s3.amazonaws.com/clusterhq-archive/centos/clusterhq-release$(rpm -E %dist).noarch.rpm
sudo yum install -y --enablerepo=clusterhq-testing clusterhq-flocker-node

sudo systemctl enable docker.service
sudo systemctl start docker.service

sudo mkdir -p /var/opt/flocker
sudo truncate --size 10G /var/opt/flocker/pool-vdev
sudo zpool create flocker /var/opt/flocker/pool-vdev

/opt/flocker/bin/trial flocker
