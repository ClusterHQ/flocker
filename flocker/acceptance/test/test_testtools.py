# Copyright ClusterHQ Ltd.  See LICENSE file for details.

"""
Tests for flocker.acceptance.testtools.
"""

from twisted.trial.unittest import SynchronousTestCase

from ..testtools import (log_method, _ensure_encodeable)


class TestLogMethod(SynchronousTestCase):

    def test_nothing(self):
        """
        We can run tests.
        """
        log_method
        _ensure_encodeable
