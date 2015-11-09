# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Base classes for unit tests.
"""

import testtools
from testtools.deferredruntest import AsynchronousDeferredRunTest

from twisted.trial import unittest


class TestCase(unittest.SynchronousTestCase):
    """
    Base class for synchronous test cases.
    """


def async_runner(timeout):
    """
    Make a ``RunTest`` instance for asynchronous tests.

    :param float timeout: The maximum length of time (in seconds) that a test
        is allowed to take.
    """
    return AsynchronousDeferredRunTest.make_factory(timeout=timeout)


# By default, asynchronous tests are timed out after 2 minutes.
DEFAULT_ASYNC_TIMEOUT = 120


class AsyncTestCase(testtools.TestCase):
    """
    Base class for asynchronous test cases.
    """

    run_tests_with = async_runner(timeout=DEFAULT_ASYNC_TIMEOUT)
