#!/bin/bash
# Set up Volume Hub if a token has been supplied.
set -ex

: ${volumehub_token:?}
: ${flocker_node_type:?}

if test -n "${volumehub_token}"; then
    export TOKEN="${volumehub_token}"

    if test "${flocker_node_type}" == "control"; then
        export TARGET="control-service"
        curl -ssL https://get-volumehub.clusterhq.com/ |sh
    fi

    if test "${flocker_node_type}" == "agent"; then
        : ${flocker_agent_number:?}
        export TARGET="agent-node"
        if test "${flocker_agent_number}" -eq "1"; then
            export RUN_FLOCKER_AGENT_HERE="1"
        fi
        curl -ssL https://get-volumehub.clusterhq.com/ |sh
    fi
fi
