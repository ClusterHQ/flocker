#!/bin/bash
#
# Small script to start the docker daemon and pull docker images so they are
# cached for use in the tutorial later.

# Error on any failure of a simple command.
set -e

# Start or restart the docker daemon.
systemctl restart docker

# Record the version of docker for the logs.
echo "Docker Version:"
docker --version

# Pull docker images so they are cached for later.
IMAGES="busybox"
IMAGES+=" clusterhq/mongodb"
IMAGES+=" redis"
IMAGES+=" python:2.7-slim"
IMAGES+=" clusterhq/flask"
for I in $IMAGES
do
    echo Pulling image $I...
    docker pull $I
done
