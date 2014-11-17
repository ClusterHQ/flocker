#!/bin/bash
yum install -y docker
sed -i 's/OPTIONS=\(.*\)/OPTIONS=\1 -H tcp:\/\/0.0.0.0:4243 -H unix:\/\/\/var\/run\/docker.sock/g' /etc/sysconfig/docker
service docker restart

# enable root login, key authentication will still need to be setup
sed -i 's/PermitRootLogin .*/PermitRootLogin yes/g' /etc/ssh/sshd_config
service sshd restart

# install zfs for flocker
KERNEL_RELEASE=`uname -r`
yum install -y https://download.fedoraproject.org/pub/epel/7/x86_64/e/epel-release-7-2.noarch.rpm
yum install -y kernel-devel-$KERNEL_RELEASE kernel-headers-$KERNEL_RELEASE 
yum localinstall -y --nogpgcheck http://archive.zfsonlinux.org/epel/zfs-release.el7.noarch.rpm
yum install -y zfs

# install flocker
yum install -y git gcc python-pip python-devel
pip install --upgrade pip
pip install --quiet https://storage.googleapis.com/archive.clusterhq.com/downloads/flocker/Flocker-0.3.0-py2-none-any.whl

# create zfs pool
mkdir -p /opt/flocker
truncate --size 1G /opt/flocker/pool-vdev
zpool create flocker /opt/flocker/pool-vdev

