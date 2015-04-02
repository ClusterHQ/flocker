#!/bin/sh

set -e -x

mkdir -p /tmp/kernel-packages
cd /tmp/kernel-packages
wget 'http://kernel.ubuntu.com/~kernel-ppa/mainline/v3.18-vivid/linux-headers-3.18.0-031800-generic_3.18.0-031800.201412071935_amd64.deb'
wget 'http://kernel.ubuntu.com/~kernel-ppa/mainline/v3.18-vivid/linux-headers-3.18.0-031800_3.18.0-031800.201412071935_all.deb'
wget 'http://kernel.ubuntu.com/~kernel-ppa/mainline/v3.18-vivid/linux-image-3.18.0-031800-generic_3.18.0-031800.201412071935_amd64.deb'
sudo dpkg -i /tmp/kernel-packages/linux-*.deb
rm -r /tmp/kernel-packages
