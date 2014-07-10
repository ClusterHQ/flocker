#!/bin/sh

set -e

# Configure pip repositories
mkdir ~/.pip
cat > ~/.pip/pip.conf <<EOF
[global]
find-links = https://s3-us-west-2.amazonaws.com/clusterhq-wheelhouse/fedora20-x86_64/index
find-links = file:///var/cache/wheelhouse
EOF
