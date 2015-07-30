#!/bin/sh
set -e

SUFFIX="${HOSTNAME}_$(date +%s)"
ARCHIVE_NAME="clusterhq_flocker_logs_${SUFFIX}"
# Export all logs into a single directory
mkdir "${ARCHIVE_NAME}"
# Export the raw Eliot log messages from all enabled Flocker services
systemctl  list-unit-files --no-legend \
| awk '$1~/^flocker-\S+\.service$/ && $2=="enabled" {print $1}' \
| while read unitname; do
    journalctl --all --output=cat --unit="${unitname}" | gzip > "${ARCHIVE_NAME}/${unitname}-${SUFFIX}.log.gz"
done

# Export the full journal since last boot with UTC timestamps
journalctl --all --boot | gzip > "${ARCHIVE_NAME}/all-${SUFFIX}.log.gz"

# Export Docker version and configuration
docker info | gzip > "${ARCHIVE_NAME}/docker_info-${SUFFIX}.gz"
docker version | gzip > "${ARCHIVE_NAME}/docker_version-${SUFFIX}.gz"

# Kernel version
uname -a > "${ARCHIVE_NAME}/uname_a-${SUFFIX}"

# Distribution version
cp /etc/os-release "${ARCHIVE_NAME}/os_release-${SUFFIX}" || true

# Create a single archive file
tar --create --file "${ARCHIVE_NAME}.tar" "${ARCHIVE_NAME}"
rm -rf "${ARCHIVE_NAME}"
