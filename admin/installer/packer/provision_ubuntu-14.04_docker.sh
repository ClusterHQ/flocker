#!/bin/bash
set -ex

# Install Docker like Vagrant does
# https://github.com/mitchellh/vagrant/blob/master/plugins/provisioners/docker/cap/debian/docker_install.rb#L13
apt-get update -qq -y
apt-get install -qq -y --force-yes curl
apt-get purge -qq -y lxc-docker* || true
curl -sSL https://get.docker.com/ | sh
