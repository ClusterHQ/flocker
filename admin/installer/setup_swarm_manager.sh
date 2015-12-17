#!/bin/bash
# Generate a swarm cluster ID, upload it to S3 and start the Swarm manager.
set -ex

: ${s3_bucket:?}

rm -rf /tmp/swarm-config
mkdir -p /tmp/swarm-config
# Create a new swarm cluster
docker pull swarm
docker run --rm swarm create > /tmp/swarm-config/swarm_cluster_id
/usr/bin/s3cmd put --config=/root/.s3cfg --recursive /tmp/swarm-config/ s3://${s3_bucket}/swarm-config/

# Start the Swarm manager
swarm_cluster_id=$(cat /tmp/swarm-config/swarm_cluster_id)
docker run -d -p 2376:2375 swarm manage token://$swarm_cluster_id
