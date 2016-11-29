#!/bin/bash
# Install and configure S3 with a minimal configuration file.
#
set -ex

: ${access_key_id:?}
: ${secret_access_key:?}

cat <<EOF > /root/.s3cfg
[default]
access_key = ${access_key_id}
secret_key = ${secret_access_key}
EOF

retry_command apt-get --yes install s3cmd

# Wrapper around S3 command to allow retry until
# bucket of interest is available and populated.
s3cmd_wrapper () {
    retry_command /usr/bin/s3cmd --force $@
}
