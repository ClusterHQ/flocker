#!/bin/bash
# Flocker Configuration Getter
#
# Downloads and installs Flocker configuration from an S3 bucket.
set -ex

: ${s3_bucket:?}
: ${node_number:?}

FLOCKER_CONFIG_DIRECTORY="/etc/flocker"
TMP_DIR="$(mktemp --directory '/etc/flocker.XXXXXXXXXX')"
/usr/bin/s3cmd get --config=/root/.s3cfg s3://${s3_bucket}/${node_number}/* "${TMP_DIR}"
if test -d "${FLOCKER_CONFIG_DIRECTORY}"; then
    mv "${FLOCKER_CONFIG_DIRECTORY}"{,.backup.$(date +%s)}
fi
chmod --recursive a-rwx,u+rwX "${TMP_DIR}"
mv "${TMP_DIR}" "${FLOCKER_CONFIG_DIRECTORY}"

if test "${node_number}" -eq "0"; then
    service flocker-control restart
else
    service flocker-control stop
fi

for service_name in flocker-{container,dataset}-agent flocker-docker-plugin; do
    service "${service_name}" restart
done
