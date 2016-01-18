#!/bin/bash
# Pull image for Docker Swarm and start Swarm Manager with TLS.

set -ex

: ${s3_bucket:?}

# Default directory where Docker (started as root) looks for certificates.
DOCKER_CERT_HOME='/root/.docker'

# Create Swarm cluster, and publish Swarm cluster ID to S3 bucket.
rm -rf /tmp/swarm-config
mkdir -p /tmp/swarm-config
docker pull swarm:1.0.1
docker run --rm -v ${DOCKER_CERT_HOME}:${DOCKER_CERT_HOME} swarm create > /tmp/swarm-config/swarm_cluster_id
/usr/bin/s3cmd put --config=/root/.s3cfg --recursive /tmp/swarm-config/ s3://${s3_bucket}/swarm-config/

# Start Swarm Manager.
swarm_cluster_id=$(cat /tmp/swarm-config/swarm_cluster_id)
docker run -d -v ${DOCKER_CERT_HOME}:${DOCKER_CERT_HOME} -p 2376:2375 swarm manage --tlsverify --tlscacert=${DOCKER_CERT_HOME}/ca.pem --tlskey=${DOCKER_CERT_HOME}/key.pem --tlscert=${DOCKER_CERT_HOME}/cert.pem token://$swarm_cluster_id
