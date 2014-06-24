#!/bin/sh

# Script to build binary rpms of zfs kernel modules.
# Run this in the vagrant image, and it will create a
# yum repository in zfs-kmod.

set -e

cd ~
git clone https://github.com/zfsonlinux/zfs.git
git clone https://github.com/zfsonlinux/spl.git

pushd spl
./autogen.sh
./configure
make rpm-kmod
sudo yum localinstall -y *.rpm
popd

pushd zfs
./autogen.sh
./configure
make rpm-kmod
popd

mkdir -p /vagrant/zfs-kmod
cp {spl,zfs}/*.rpm /vagrant/zfs-kmod
createrepo /vagrant/zfs-kmod
