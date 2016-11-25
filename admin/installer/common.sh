#!/bin/bash
#
# Shared helper functions.
#
# set -ex

# Retry a command line until it succeeds.
# With a delay between attempts and a limited number of attempts.

RETRY_COMMAND_SLEEP_INTERVAL=5
RETRY_COMMAND_RETRY_LIMIT=5

function retry_command () {
    local count=0
    local last_return_code=1
    echo "RETRY_COMMAND_SLEEP_INTERVAL=${RETRY_COMMAND_SLEEP_INTERVAL}" >&2
    echo "RETRY_COMMAND_RETRY_LIMIT=${RETRY_COMMAND_RETRY_LIMIT}" >&2

    while true; do
        count=$((count+1))
        "${@}"
        last_return_code=$?
        if [[ "${last_return_code}" -eq 0 ]]; then
            return 0
        fi
        if [[ "${count}" -eq "${RETRY_COMMAND_RETRY_LIMIT}" ]]; then
            break
        fi

        echo "RETRY_COMMAND: command '${@}' failed with exit_code '${last_return_code}'" >&2
        echo "RETRY_COMMAND: failure_count: ${count}"
        echo "RETRY_COMMAND: sleeping for ${RETRY_COMMAND_SLEEP_INTERVAL}s" >&2
        sleep "${RETRY_COMMAND_SLEEP_INTERVAL}"
    done
    echo "RETRY_COMMAND: stopping after '${RETRY_COMMAND_RETRY_LIMIT}' failed attempts" >&2
    return ${last_return_code}
}
