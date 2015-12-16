#!/bin/bash
# Create and join a Swarm node to a Swarm cluster identified by cluster id in S3 bucket.
set -ex

: ${s3_bucket:?}

# Gather Swarm cluster id from S3 bucket.
swarm_cluster_id=$(/usr/bin/s3cmd get --config=/root/.s3cfg s3://${s3_bucket}/swarm-config/swarm_cluster_id -) 

# Start the Swarm node.
docker run -d swarm join --addr=$(/usr/bin/ec2metadata --local-ipv4):2375 token://$swarm_cluster_id
