#!/bin/sh

# Pre-cache downloads.

set -e

# Precache zfs rpms.
# We don't install them, since the result of installing dkms modules
# is not redistrubtable (GPL vs CDDL)
yum install --downloadonly zfs

# Download docker images used.
systemctl start docker
docker pull busybox
docker pull openshift/busybox-http-app

# Download python wheels
mkdir /var/cache/wheelhouse
wget -r -nd -P /var/cache/wheelhouse https://s3-us-west-2.amazonaws.com/clusterhq-wheelhouse/fedora20-x86_64/index
