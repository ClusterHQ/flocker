#!/bin/bash
set -ex
rm -rf /tmp/flocker-config
mkdir /tmp/flocker-config
cd /tmp/flocker-config
cat <<EOF >/tmp/flocker-config/.s3cfg
[default]
access_key = ${access_key_id}
secret_key = ${secret_access_key}
EOF

apt-get -y install s3cmd

rm -rf /tmp/s3-flocker-config
mkdir /tmp/s3-flocker-config
/usr/bin/s3cmd get --verbose --config=/tmp/flocker-config/.s3cfg s3://${s3_bucket}/${node_number}/* /tmp/s3-flocker-config/
rm -rf /etc/flocker
mv /tmp/s3-flocker-config /etc/flocker
chmod --recursive a-rwx,u+rwX /etc/flocker
