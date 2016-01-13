#!/bin/bash
# Generate certs for {Docker, Swarm} TLS and start Swarm Manager.
set -ex

: ${s3_bucket:?}

DOCKER_CERT_HOME='/root/.docker'

# Create a new swarm cluster
rm -rf /tmp/swarm-config
mkdir -p /tmp/swarm-config
docker pull swarm:1.0.1
docker run --rm -v ${DOCKER_CERT_HOME}:${DOCKER_CERT_HOME} swarm create > /tmp/swarm-config/swarm_cluster_id
/usr/bin/s3cmd put --config=/root/.s3cfg --recursive /tmp/swarm-config/ s3://${s3_bucket}/swarm-config/

# Start the Swarm manager
swarm_cluster_id=$(cat /tmp/swarm-config/swarm_cluster_id)
docker run -d -v ${DOCKER_CERT_HOME}:${DOCKER_CERT_HOME} -p 2376:2375 swarm manage --tlsverify --tlscacert=${DOCKER_CERT_HOME}/ca.pem --tlskey=${DOCKER_CERT_HOME}/key.pem --tlscert=${DOCKER_CERT_HOME}/cert.pem token://$swarm_cluster_id
