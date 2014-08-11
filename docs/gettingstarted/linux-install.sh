#!/bin/sh

# Create a virtualenv, an isolated Python environment, in a new directory called
# "flocker-tutorial":
virtualenv --python=/usr/bin/python2.7 flocker-tutorial

# Upgrade the pip Python package manager to its latest version inside the
# virtualenv. Some older versions of pip have issues installing Python wheel
# packages.
flocker-tutorial/bin/pip install --upgrade pip

# Install flocker-cli and dependencies inside the virtualenv:
echo "Installing Flocker and dependencies, this may take a few minutes..."
flocker-tutorial/bin/pip install --quiet https://storage.googleapis.com/archive.clusterhq.com/downloads/flocker/Flocker-0.0.6-py2-none-any.whl
