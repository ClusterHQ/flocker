#!/bin/sh

# Pre-cache downloads.

set -e

# Download docker images used.
systemctl start docker
docker pull busybox
docker pull openshift/busybox-http-app

# Download python wheels
mkdir /var/cache/wheelhouse
wget --no-directories --directory-prefix /var/cache/wheelhouse \
     --input-file https://s3-us-west-2.amazonaws.com/clusterhq-wheelhouse/fedora20-x86_64/index
