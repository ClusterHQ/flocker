#!/bin/bash
# Set up Volume Hub if a token has been supplied.
set -ex

: ${volumehub_token:?}
: ${node_number:?}

if test -z "${volumehub_token}"; then
    # No Volume Hub token supplied.
    exit
fi

control_service=false
agent_node=false
agent_number="0"

if test "${node_number}" -eq "0"; then
    control_service=true
else
    agent_node=true
    # This only works because we start numbering CloudFormation nodes at 0.
    agent_number="${node_number}"
fi

export TOKEN="${volumehub_token}"

if ${control_service}; then
    export TARGET="control-service"
    curl -ssL https://get-volumehub.clusterhq.com/ |sh
fi

if ${agent_node}; then
    export TARGET="agent-node"
    if test "${agent_number}" -eq "1"; then
        export RUN_FLOCKER_AGENT_HERE="1"
    fi
    curl -ssL https://get-volumehub.clusterhq.com/ |sh
fi
