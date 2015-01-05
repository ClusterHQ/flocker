#!/bin/sh

# Pre-cache downloads.

set -e

# We indirectly ask Docker to write a very large file to its temporary
# directory.  /tmp is a small tmpfs mount which can't hold the file.  Convince
# Docker to write somewhere else instead.
echo "# Flocker-defined alternate temporary path to provide more temporary space." >> /etc/sysconfig/docker
echo "TMPDIR=/var/tmp" >> /etc/sysconfig/docker

# Restart docker to ensure that it picks up the new tmpdir configuration.
systemctl restart docker

while read image; do
    docker pull "${image}"
done <<EOF
busybox
clusterhq/mongodb
mysql:5.6.17
postgres
clusterhq/elasticsearch
clusterhq/logstash
clusterhq/kibana
EOF
