#!/bin/bash
set -ex

# Install Docker according to their distribution specific instructions:
# https://docs.docker.com/engine/installation/ubuntulinux/
apt-key adv --keyserver hkp://p80.pool.sks-keyservers.net:80 --recv-keys 58118E89F3A912897C070ADBF76221572C52609D
cat <<EOF > /etc/apt/sources.list.d/docker.list
deb https://apt.dockerproject.org/repo ubuntu-trusty main
EOF
# apt-get update fails in an Ubuntu 14.04 docker container unless you install
# this first.
apt-get install -qq -y apt-transport-https
apt-get update -qq -y
apt-get purge -qq -y lxc-docker* || true
apt-get install -qq -y "linux-image-extra-$(uname -r)" "docker-engine=${DOCKER_VERSION}*"
service docker start || true
if test -e /etc/default/ufw; then
    sed --in-place 's/DEFAULT_FORWARD_POLICY=".*"/DEFAULT_FORWARD_POLICY="ACCEPT"/g' /etc/default/ufw
    ufw reload
    ufw allow 2375/tcp
fi

# Prepull swarm
docker pull "swarm:${SWARM_VERSION:-latest}"
