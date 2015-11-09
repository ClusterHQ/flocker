# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Base classes for unit tests.
"""

from twisted.trial import unittest


class TestCase(unittest.SynchronousTestCase):
    """
    Base class for synchronous test cases.
    """


class AsyncTestCase(unittest.TestCase):
    """
    Base class for asynchronous test cases.
    """
