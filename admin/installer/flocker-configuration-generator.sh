#!/bin/bash
# Flocker Configuration Generator
#
# Generates configuration and certificates for all nodes in the cluster and
# uploads them to an S3 bucket.
set -ex

: ${aws_region:?}
: ${aws_zone:?}
: ${access_key_id:?}
: ${secret_access_key:?}
: ${node_count:?}
: ${s3_bucket:?}

control_service_ip=$(/usr/bin/ec2metadata --public-ipv4)
rm -rf /tmp/flocker-config
mkdir /tmp/flocker-config

cat <<EOF >/tmp/flocker-config/agent.yml
control-service:
    hostname: "${control_service_ip}"
    port: 4524
dataset:
    backend: "aws"
    region: "${aws_region}"
    zone: "${aws_zone}"
    access_key_id: "${access_key_id}"
    secret_access_key: "${secret_access_key}"
version: 1
EOF

pushd /tmp/flocker-config

/opt/flocker/bin/flocker-ca initialize flocker-cluster
/opt/flocker/bin/flocker-ca create-api-certificate user1

for i in $(seq 0 $((${node_count}-1))); do
    mkdir -p "${i}"
    /opt/flocker/bin/flocker-ca create-node-certificate "--outputpath=${i}"
    pushd "${i}"
    mv {*,node}.key
    mv {*,node}.crt
    cp ../cluster.crt .
    cp ../agent.yml .
    popd
    /opt/flocker/bin/flocker-ca create-api-certificate "--outputpath=${i}" plugin
done

mkdir -p 0
/opt/flocker/bin/flocker-ca create-control-certificate --outputpath=0 $control_service_ip
pushd 0
mv control-{*,service}.key
mv control-{*,service}.crt
popd

for i in $(seq 0 $((${node_count}-1))); do
    pushd "${i}"
    tar -cvf "../${i}.tar.gz" *
    popd
    rm -rf "${i}"
done

popd

/usr/bin/s3cmd put --config=/root/.s3cfg --recursive /tmp/flocker-config/ s3://${s3_bucket}/flocker-config/
