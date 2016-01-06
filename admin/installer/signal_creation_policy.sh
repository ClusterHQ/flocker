#!/bin/bash
# Signal CloudFormation that user data setup is done.

set -ex

sudo apt-get install -y python-pip python-dev
pip install heat-cfntools
export PYTHONPATH=/usr/local/lib/python2.7/dist-packages:$PATH

/usr/local/bin/cfn-signal -s SUCCESS -e 0 ${wait_condition_handle}
