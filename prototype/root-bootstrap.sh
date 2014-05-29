#!/bin/sh

# Some thing we need to build stuff:
yum groupinstall "Development tools"
yum install kernel-headers kernel-devel zlib-devel libuuid-devel libselinux-devel rpmdevtools
yum install autoconf automake rpm-devel libtool
yum install gcc make perl dkms
yum install bc lsscsi mdadm

