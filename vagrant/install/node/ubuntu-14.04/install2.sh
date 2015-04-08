#!/bin/sh

set -e -x

FLOCKER_VERSION=$1
if [ -z "${FLOCKER_VERSION}" ]; then
	echo "$0 <FLOCKER_VERSION>" >&2
	exit 1
fi

sudo add-apt-repository -y ppa:zfs-native/stable
sudo add-apt-repository -y ppa:james-page/docker
sudo add-apt-repository -y 'deb http://build.clusterhq.com/results/omnibus/master/ubuntu-14.04 /'
sudo apt-get update
# sudo apt-get -y upgrade
sudo apt-get -y install spl-dkms
sudo apt-get -y install zfs-dkms zfsutils docker.io

# Unauthenticated packages need --force-yes
sudo apt-get -y --force-yes install clusterhq-python-flocker clusterhq-flocker-node

sudo mkdir -p /var/opt/flocker
sudo truncate --size 10G /var/opt/flocker/pool-vdev
sudo zpool create flocker /var/opt/flocker/pool-vdev

/opt/flocker/bin/trial flocker
