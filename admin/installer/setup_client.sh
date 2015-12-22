#!/bin/bash
# Setup up a client compute instance to deploy sample workloads on an install
# cluster using docker-compose.

set -ex

apt-get update
sudo apt-get install -y postgresql-client

curl -L https://github.com/docker/compose/releases/download/1.5.2/docker-compose-`uname -s`-`uname -m` > /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

mkdir -p /home/ubuntu/postgres

curl https://raw.githubusercontent.com/ClusterHQ/flocker/b371c64fc5f50801f2cce34d31ea3700f7cab024/admin/installer/postgres/docker-compose-node0.yml > /home/ubuntu/postgres/docker-compose-node0.yml

chown --recursive ubuntu:ubuntu /home/ubuntu/postgres
