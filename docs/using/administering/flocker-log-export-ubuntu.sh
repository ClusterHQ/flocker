#!/bin/sh
set -e

SUFFIX="${HOSTNAME}_$(date +%s)"
ARCHIVE_NAME="clusterhq_flocker_logs_${SUFFIX}"
# Export all logs into a single directory
mkdir "${ARCHIVE_NAME}"
# Export the raw Eliot log messages from all enabled Flocker services
find /var/log/flocker -type f \
| xargs --max-args=1 --replace='{}' -- basename {} '.log'  \
| while read filename; do
    gzip < "/var/log/flocker/${filename}.log" > "${ARCHIVE_NAME}/${filename}-${SUFFIX}.log.gz"
done
# Export the full syslog since last boot with UTC timestamps
gzip < /var/log/syslog > "${ARCHIVE_NAME}/all-${SUFFIX}.log.gz"
# Create a single archive file
tar --create --file "${ARCHIVE_NAME}.tar" "${ARCHIVE_NAME}"
rm -rf "${ARCHIVE_NAME}"
