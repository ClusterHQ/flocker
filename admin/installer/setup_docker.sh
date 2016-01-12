#!/bin/bash
# Get TLS certs and restart Docker daemon.
set -ex

: ${node_number:?}
: ${s3_bucket:?}

# Turn off TLS authentication.
# cat <<EOF > /etc/default/docker
# DOCKER_OPTS="-H unix:///var/run/docker.sock -H=0.0.0.0:2375 --label flocker-node=${node_number}"
# EOF

# Get TLS from S3 bucket.
ROOT_DOCKER_TLS_CONFIG_DIRECTORY="/root/.docker/"
UBUNTU_HOME="/home/ubuntu"
rm -rf ${ROOT_DOCKER_TLS_CONFIG_DIRECTORY} ${UBUNTU_HOME}/.docker
mkdir -p ${ROOT_DOCKER_TLS_CONFIG_DIRECTORY}
s3cmd get --recursive --config=/root/.s3cfg s3://${s3_bucket}/docker-swarm-tls-config/ "${ROOT_DOCKER_TLS_CONFIG_DIRECTORY}"
cp -r "${ROOT_DOCKER_TLS_CONFIG_DIRECTORY}" "${UBUNTU_HOME}"


# Remove the docker machine ID (this is a cloned AMI)
rm -f /etc/docker/key.json
# Restart which will stop any existing containers.
service docker restart
