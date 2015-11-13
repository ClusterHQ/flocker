# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Operations tests for the control service benchmarks.
"""

from zope.interface.verify import verifyObject

from twisted.trial.unittest import TestCase

from benchmark.operations import NoOperation, ReadRequest
from benchmark._operations import IProbe, IOperation


def check_interfaces(factory):

    class OperationTests(TestCase):

        def test_interfaces(self):
            operation = factory(control_service=None)
            verifyObject(IOperation, operation)
            probe = operation.get_probe()
            verifyObject(IProbe, probe)

    testname = '{}InterfaceTests'.format(factory.__name__)
    OperationTests.__name__ = testname
    globals()[testname] = OperationTests

for factory in (NoOperation, ReadRequest):
    check_interfaces(factory)
