#!/bin/bash
# Flocker Configuration Getter
#
# Downloads and installs Flocker configuration from an S3 bucket.
set -ex

: ${s3_bucket:?}
: ${node_number:?}

FLOCKER_CONFIG_DIRECTORY="/etc/flocker"
TMP_DIR="$(mktemp --directory '/etc/flocker.XXXXXXXXXX')"
archive_path="/tmp/flocker-config.${node_number}.tar.gz"
s3cmd_wrapper get --config=/root/.s3cfg s3://${s3_bucket}/flocker-config/${node_number}.tar.gz "${archive_path}"

pushd "${TMP_DIR}"
tar xf "${archive_path}"
popd

if test -d "${FLOCKER_CONFIG_DIRECTORY}"; then
    mv "${FLOCKER_CONFIG_DIRECTORY}"{,.backup.$(date +%s)}
fi
chmod --recursive a-rwx,u+rwX "${TMP_DIR}"
mv "${TMP_DIR}" "${FLOCKER_CONFIG_DIRECTORY}"

if test "${node_number}" -eq "0"; then
    service flocker-control restart

    for service_name in flocker-{container,dataset}-agent flocker-docker-plugin; do
        service "${service_name}" stop || true
    done
else
    service flocker-control stop || true

    for service_name in flocker-{container,dataset}-agent flocker-docker-plugin; do
        service "${service_name}" restart
    done
fi
