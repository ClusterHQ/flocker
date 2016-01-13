#!/bin/bash
# Setup up a client compute instance to deploy sample workloads on an install
# cluster using docker-compose.

set -ex

DOCKER_CERT_HOME="/root/.docker"

apt-get update
sudo apt-get install -y postgresql-client

curl -L https://github.com/docker/compose/releases/download/1.5.2/docker-compose-`uname -s`-`uname -m` > /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

mkdir -p /home/ubuntu/postgres

curl https://raw.githubusercontent.com/ClusterHQ/flocker/flocker-cloudformation-FLOC-3709/admin/installer/postgres/docker-compose-node0.yml > /home/ubuntu/postgres/docker-compose-node0.yml
curl https://raw.githubusercontent.com/ClusterHQ/flocker/flocker-cloudformation-FLOC-3709/admin/installer/postgres/docker-compose-node1.yml > /home/ubuntu/postgres/docker-compose-node1.yml

chown --recursive ubuntu:ubuntu /home/ubuntu/postgres

# Get uft-flocker-volumes
curl -sSL https://get.flocker.io/ | sh

mkdir -p /etc/flocker
s3cmd_wrapper get --recursive --config=/root/.s3cfg s3://${s3_bucket}/flocker-config/ /etc/flocker

# Get certs for talking to Docker Swarm
s3cmd get --force --config=/root/.s3cfg s3://${s3_bucket}/docker-swarm-tls-config/client-cert.pem "${DOCKER_CERT_HOME}"/client-cert.pem
s3cmd get --force --config=/root/.s3cfg s3://${s3_bucket}/docker-swarm-tls-config/client-key.pem "${DOCKER_CERT_HOME}"/client-key.pem
