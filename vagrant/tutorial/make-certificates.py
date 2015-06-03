#!/usr/bin/env python

# Copyright ClusterHQ Inc.  See LICENSE file for details.
# Generates a set of cluster, node and user certificates and keys for
# use with the tutorial Vagrant box.

from twisted.python.filepath import FilePath
from flocker.provision._ca import Certificates

Certificates.generate(
    FilePath(__file__).sibling('credentials'),
    '172.16.255.250',
    2
)
