#!/usr/bin/env python

from twisted.python.filepath import FilePath
from flocker.provision._ca import Certificates

Certificates.generate(
    FilePath(__file__).sibling('credentials'),
    '172.16.255.250',
    2
)
