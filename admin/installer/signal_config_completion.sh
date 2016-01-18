#!/bin/bash
# Signal CloudFormation that user data setup is done.

set -ex

curl -v -X PUT -H 'Content-Type:' \
    -d '{"Status" : "SUCCESS","Reason" : "Configuration OK","UniqueId" : "FlockerSwarm","Data" : "Flocker and Swarm configured."}' \
    "${wait_condition_handle}"
