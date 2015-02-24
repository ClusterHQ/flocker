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

for image in busybox clusterhq/mongodb dockerfile/redis clusterhq/flask; do
    docker pull "${image}"
done


## Hacks to demonstrate other changes
systemctl enable firewalld
systemctl start firewalld
for PORT in 3306 9200 5000 80 5432 27018; do # List of ports used in acceptance tests
    for DEST in 172.16.255.240 172.16.255.241; do # List of vagrant nodes
        # Extra rules for proxies
        firewall-cmd --permanent --add-rule ipv4 filter FORWARD 0 --destination $DEST --protocol tcp --desitnation-port $PORT -j ACCEPT
    done
    # New rule for open ports
    firewall-cmd --permanent --add-rule ipv4 filter INPUT 0 --protocol tcp --desitnation-port $PORT -j ACCEPT
done
