#!/bin/sh

# Install required system packages:
sudo apt-get install python2.7 python-virtualenv python-pip python2.7-dev

# Create a virtualenv, an isolated Python environment, in a new directory called
# "flocker-tutorial":
virtualenv --python=/usr/bin/python2.7 flocker-tutorial

# Upgrade the pip Python package manager to its latest version inside the
# virtualenv:
flocker-tutorial/bin/pip install --upgrade pip

# Install flocker-cli and dependencies inside the virtualenv:
# XXX change to real 0.1.0 URL as part of https://github.com/ClusterHQ/flocker/issues/359:
flocker-tutorial/bin/pip install https://github.com/ClusterHQ/flocker/archive/master.zip
