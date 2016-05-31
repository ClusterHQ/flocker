# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.node._generations``.
"""

from testtools.matchers import Equals

from ...testtools import TestCase

from ..testtools import deployment_strategy
from .._generations import GenerationTracker
from .._persistence import make_generation_hash


class GenerationTrackerTests(TestCase):

    def test_baic_use_works(self):
        deployments = list(deployment_strategy() for _ in xrange(5))
        tracker_under_test = GenerationTracker(10)
        for d in tracker_under_test:
            self.get_diff_from_hash_to_latest(None, d)

        last_deployment = deployments[-1]

        for d in tracker_under_test:
            diff = self.get_diff_from_hash_to_latest(
                make_generation_hash(d), last_deployment)
            self.assertThat(
                diff.apply(d),
                Equals(last_deployment)
            )
