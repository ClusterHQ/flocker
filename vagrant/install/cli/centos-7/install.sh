#!/bin/sh

set -e -x

FLOCKER_VERSION=$1
if [ -z "${FLOCKER_VERSION}" ]; then
	echo "$0 <FLOCKER_VERSION>" >&2
	exit 1
fi

VIRTUAL_ENV=flocker-cli-centos

sudo yum install -y gcc python python-devel python-virtualenv

virtualenv --python=/usr/bin/python2.7 ${VIRTUAL_ENV}

${VIRTUAL_ENV}/bin/pip install --upgrade pip

${VIRTUAL_ENV}/bin/pip install https://storage.googleapis.com/archive.clusterhq.com/downloads/flocker/Flocker-${FLOCKER_VERSION}-py2-none-any.whl

version=`${VIRTUAL_ENV}/bin/flocker-deploy --version`
if [ "${version}" != "${FLOCKER_VERSION}" ]; then
	echo "Expected version ${FLOCKER_VERSION}, got version ${version}" >&2
	exit 1
fi

echo "Flocker CLI ${version} installed."

${VIRTUAL_ENV}/bin/trial flocker.cli
