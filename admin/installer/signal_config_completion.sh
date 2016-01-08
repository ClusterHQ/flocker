#!/bin/bash
# Signal CloudFormation that user data setup is done.

set -ex

sudo apt-get install -y python-pip python-dev
pip install heat-cfntools
export PYTHONPATH=/usr/local/lib/python2.7/dist-packages:$PATH

curl -v -X PUT -H 'Content-Type:' \
    -d '{"Status" : "SUCCESS","Reason" : "Configuration OK","UniqueId" : "FlockerSwarm","Data" : "Flocker and Swarm configured."}' \
    "${wait_condition_handle}"
