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
# Create a single archive file
tar --create --file "${ARCHIVE_NAME}.tar" "${ARCHIVE_NAME}"
rm -rf "${ARCHIVE_NAME}"
