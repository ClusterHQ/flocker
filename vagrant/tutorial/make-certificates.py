#!/usr/bin/env python

# Copyright ClusterHQ Inc.  See LICENSE file for details.

from twisted.python.filepath import FilePath
from flocker.provision._ca import Certificates

Certificates.generate(
    FilePath(__file__).sibling('credentials'),
    '172.16.255.250',
    2
)
