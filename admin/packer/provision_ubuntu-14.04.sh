#!/bin/bash
set -ex

# Install Docker like Vagrant does
# https://github.com/mitchellh/vagrant/blob/master/plugins/provisioners/docker/cap/debian/docker_install.rb#L13
apt-get update -qq -y
apt-get install -qq -y --force-yes curl
apt-get purge -qq -y lxc-docker* || true
curl -sSL https://get.docker.com/ | sh

# Install Flocker
apt-get install -qq -y apt-transport-https software-properties-common
if test -z "${flocker_branch}"; then
    add-apt-repository -y "deb https://clusterhq-archive.s3.amazonaws.com/ubuntu/$(lsb_release --release --short)/\$(ARCH) /"
else
    add-apt-repository -y "deb http://build.clusterhq.com/results/omnibus/${flocker_branch}/ubuntu-14.04 /"
fi
apt-get update -qq -y
apt-get install -qq -y --force-yes clusterhq-flocker-node clusterhq-flocker-docker-plugin
