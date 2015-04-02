#!/bin/sh

set -e -x

FLOCKER_VERSION=$1
if [ -z "${FLOCKER_VERSION}" ]; then
	echo "$0 <FLOCKER_VERSION>" >&2
	exit 1
fi

sudo add-apt-repository -y ppa:zfs-native/stable
sudo add-apt-repository -y ppa:james-page/docker
sudo apt-get update
sudo apt-get -y upgrade
sudo apt-get -y install spl-dkms
sudo apt-get -y install zfs-dkms zfsutils docker.io

wget -O clusterhq-python-flocker http://build.clusterhq.com/results/omnibus/master/ubuntu-14.04/clusterhq-python-flocker_${FLOCKER_VERSION}_amd64.deb
wget -O clusterhq-flocker-node http://build.clusterhq.com/results/omnibus/master/ubuntu-14.04/clusterhq-flocker-node_${FLOCKER_VERSION}_all.deb
sudo dpkg -i clusterhq-python-flocker clusterhq-flocker-node

/opt/flocker/bin/trial flocker
