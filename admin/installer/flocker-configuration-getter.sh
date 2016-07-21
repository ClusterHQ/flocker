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
    # Enable flocker-control on node0 and disable the flocker agent services.
    systemctl enable flocker-control
    systemctl restart flocker-control

    for service_name in flocker-{container,dataset}-agent flocker-docker-plugin; do
        systemctl stop "${service_name}"
        systemctl disable "${service_name}"
    done
else
    # All other nodes will run flocker agent services.
    # We're using docker swarm to schedule containers so the container agent
    # is disabled.
    for service_name in flocker-container-agent flocker-control; do
        systemctl stop "${service_name}"
        systemctl disable "${service_name}"
    done

    for service_name in flocker-dataset-agent flocker-docker-plugin; do
        systemctl enable "${service_name}"
        systemctl restart "${service_name}"
    done
fi
