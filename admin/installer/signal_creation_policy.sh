#!/bin/bash
# Signal CloudFormation that user data setup is done.

set -ex

sudo apt-get install -y python-pip python-dev
pip install heat-cfntools
export PYTHONPATH=/usr/local/lib/python2.7/dist-packages:$PATH

/usr/bin/cfn-signal -s SUCCESS -e 0 --stack ${stack_name} --resource ${node_name}
