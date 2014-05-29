#!/bin/sh
sudo /vagrant/root-bootstrap.sh

# ZFS setup, until RPMs are available for Fedora 20:
cd ~
git clone https://github.com/zfsonlinux/zfs.git
git clone https://github.com/zfsonlinux/spl.git
pushd spl
./configure
make pkg
sudo rpm -i *.noarch.rpm *.x86_64.rpm
popd

pushd zfs
./configure
make pkg
sudo rpm -i *.noarch.rpm *.x86_64.rpm
popd

# Setup ZFS pool:
sudo dd if=/dev/zero of=/root/zpool count=2000000
sudo zpool create -m /zpool zpool /root/zpool
