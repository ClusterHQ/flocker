#!/bin/sh
sudo /vagrant/root-bootstrap.sh

# ZFS setup based on
# http://www.firewing1.com/howtos/fedora-20/installing-zfs-and-setting-pool
# until 0.6.3 is out:
cd ~
git clone https://github.com/zfsonlinux/zfs.git
git clone https://github.com/zfsonlinux/spl.git
pushd spl
./configure
make pkg
popd

pushd zfs
./configure
make pkg
popd

sudo yum localinstall spl/spl-[version].$(uname -m).rpm spl/spl-dkms-[version].noarch.rpm zfs/zfs-[version].$(uname -m).rpm zfs/zfs-dkms-[version].noarch.rpm
sudo systemctl enable zfs
sudo systemctl start zfs

# Setup ZFS pool:
sudo dd if=/dev/zero of=/root/zpool count=2000000
sudo zpool create -m /zpool zpool /root/zpool
