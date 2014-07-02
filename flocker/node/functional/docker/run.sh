#!/bin/sh
set -e
help() {
    cat <<EOF
Usage: run.sh [options] HOST PORT BYTES TIMEOUT

Send BYTES to HOST:PORT using a TCP connection.

Retry until a connection can be established or until the TIMEOUT period is
reached.

This is the init script for the Docker container described in the neighbouring
Dockerfile.

Options:
 --help: Print help.

EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h | --help)
            help
            exit 0
            ;;
        --)
            shift
            break
            ;;
        -*)
            help >&2
            echo "ERROR: Unknown option: $1" >&2
            exit 1
            ;;
        *)
            break
            ;;
    esac
done

HOST=${1:?"Error: Missing parameter 1:HOST"}
PORT=${2:?"Error: Missing parameter 2:PORT"}
BYTES=${3:?"Error: Missing parameter 3:BYTES"}
TIMEOUT=${4:?"Error: Missing parameter 3:TIMEOUT"}

start_time=$(date +"%s")
# Attempt to connect
# NB nc -w 10 means connection timeout after 10s
while ! echo -n "${BYTES}" | nc -w 10 "${HOST}" "${PORT}"; do
    usleep 100000
    if test "$(date +'%s')" -gt "$((start_time+${TIMEOUT}))"; then
        echo "ERROR: unable to connect to after ${TIMEOUT} seconds." >&2
        break
    fi
done
