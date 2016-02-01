#!/bin/bash
set -ex

# Install Flocker
apt-get install -qq -y apt-transport-https software-properties-common
if test -z "${flocker_branch}"; then
    add-apt-repository -y "deb https://clusterhq-archive.s3.amazonaws.com/ubuntu/$(lsb_release --release --short)/\$(ARCH) /"
else
    add-apt-repository -y "deb http://build.clusterhq.com/results/omnibus/${flocker_branch}/ubuntu-14.04 /"
fi
apt-get update -qq -y
apt-get install -qq -y --force-yes clusterhq-flocker-node clusterhq-flocker-docker-plugin
