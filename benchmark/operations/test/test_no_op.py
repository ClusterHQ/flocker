# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Operations tests for the control service benchmarks.
"""
from zope.interface.verify import verifyClass

from flocker.testtools import TestCase

from benchmark._interfaces import IOperation
from benchmark.operations import NoOperation


class NoOpTests(TestCase):

    def test_implements_IOperation(self):
        """
        NoOp provides the IOperation interface.
        """
        verifyClass(IOperation, NoOperation)
