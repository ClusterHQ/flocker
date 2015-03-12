#!/bin/sh

# Pre-cache downloads.

set -e

# Download docker images used.
systemctl start docker
docker pull busybox
docker pull openshift/busybox-http-app

