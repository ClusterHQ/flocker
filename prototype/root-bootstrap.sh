#!/bin/sh

# Some thing we need to build stuff:
yum groupinstall "Development tools"
yum install kernel-headers kernel-devel zlib-devel libuuid-devel libselinux-devel rpmdevtools

# ZFS setup based on
# http://www.firewing1.com/howtos/fedora-20/installing-zfs-and-setting-pool
# until 0.6.3 is out:
cd /tmp
git clone https://github.com/zfsonlinux/zfs.git
git clone https://github.com/zfsonlinux/spl.git
pushd spl
./autogen.sh
make rpm-utils rpm-dkms
popd

pushd zfs
./autogen.sh
make rpm-utils rpm-dkms
popd

yum localinstall spl/spl-[version].$(uname -m).rpm spl/spl-dkms-[version].noarch.rpm zfs/zfs-[version].$(uname -m).rpm zfs/zfs-dkms-[version].noarch.rpm
systemctl enable zfs
systemctl start zfs


# Setup ZFS pool:
dd if=/dev/zero of=/root/zpool count=2000000
zpool create -m /zpool zpool /root/zpool
