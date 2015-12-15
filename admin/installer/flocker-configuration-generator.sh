#!/bin/bash
set -ex
control_service_ip=`/usr/bin/ec2metadata --public-ipv4`
rm -rf /tmp/flocker-config
mkdir /tmp/flocker-config
cd /tmp/flocker-config

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

cat <<EOF >/tmp/flocker-config/.s3cfg
[default]
access_key = ${access_key_id}
secret_key = ${secret_access_key}
EOF

/opt/flocker/bin/flocker-ca initialize flocker-cluster

/opt/flocker/bin/flocker-ca create-api-certificate user1
for i in $(seq 0 $(($num_nodes-1))); do
    mkdir -p $i
    /opt/flocker/bin/flocker-ca create-node-certificate "--outputpath=$i"
    pushd "$i"
    mv {*,node}.key
    mv {*,node}.crt
    cp ../cluster.crt .
    cp ../agent.yml .
    cp ../.s3cfg .
    popd
done

mkdir -p 0
/opt/flocker/bin/flocker-ca create-control-certificate --outputpath=0 $control_service_ip
pushd 0
mv control-{*,service}.key
mv control-{*,service}.crt
popd 

apt-get -y install s3cmd

/usr/bin/s3cmd put --verbose --config=/tmp/flocker-config/.s3cfg --recursive /tmp/flocker-config/ s3://${s3_bucket}
mv /tmp/flocker-config/0/* /etc/flocker
