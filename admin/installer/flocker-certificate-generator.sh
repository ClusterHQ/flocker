#!/bin/bash
set -ex
control_service_ip=`/usr/bin/ec2metadata --public-ipv4`
rm -rf /tmp/flocker-config
mkdir /tmp/flocker-config
cd /tmp/flocker-config
/opt/flocker/bin/flocker-ca initialize flocker-cluster

/opt/flocker/bin/flocker-ca create-api-certificate user1
for i in $(seq 0 $(($num_nodes-1))); do
    mkdir -p $i
    /opt/flocker/bin/flocker-ca create-node-certificate "--outputpath=$i"
    pushd "$i"
    mv {*,node}.key
    mv {*,node}.crt
    cp ../cluster.crt .
    popd
done

mkdir -p 0
/opt/flocker/bin/flocker-ca create-control-certificate --outputpath=0 $control_service_ip
pushd 0
mv control-{*,service}.key
mv control-{*,service}.crt
popd 
