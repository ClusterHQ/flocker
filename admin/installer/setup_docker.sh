#!/bin/bash
# Resconfigure and restart Docker daemon.
set -ex

: ${node_number:?}

# Turn off TLS authentication.
cat <<EOF > /etc/default/docker
DOCKER_OPTS="-H unix:///var/run/docker.sock -H=0.0.0.0:2375 --label flocker-node=${node_number}"
EOF
# Remove the docker machine ID (this is a cloned AMI)
rm -f /etc/docker/key.json
# Restart which will stop any existing containers.
service docker restart
