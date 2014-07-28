#!/usr/bin/env bash

# Flocker CLI running against live code base

# Install by symlinking this file into your executbales path, eg;
# `sudo ln -s $(pwd)/flocker-deploy-dev /usr/local/bin/fl-dev'

set -e

FLOCKER_ROOT="$(dirname "$(test -L "$0" && readlink "$0" || echo "$0")")/.."

if [ ! -d "$FLOCKER_ROOT/env" ]; then
	printf "Please setup Virtualenv at 'env/'"
	echo " and install dependencies with \`python setup.py install .[doc,dev]'"
 	exit 1
fi

$FLOCKER_ROOT/env/bin/python \
	-c 'from flocker.cli.script import flocker_deploy_main; flocker_deploy_main()' $@
