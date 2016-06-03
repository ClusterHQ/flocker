# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.node._generations``.
"""

from testtools.matchers import Equals, Is, Not

from ...testtools import TestCase

from ..testtools import deployment_strategy
from .._generations import GenerationTracker
from .._persistence import make_generation_hash


class GenerationTrackerTests(TestCase):

    def test_basic_use_works(self):
        """
        After inserting a bunch of deployments into a ``GenerationTracker`` in
        sequence, the ``Diff`` returned from ``get_diff_from_hash_to_latest``
        can be applied to convert each of the deployments to the latest
        deployment.
        """
        deployments = list(deployment_strategy().example() for _ in xrange(5))
        deployments[3] = deployments[1]
        tracker_under_test = GenerationTracker(10)
        for d in deployments:
            tracker_under_test.insert_latest(d)

        last_deployment = deployments[-1]

        for d in deployments:
            last = None
            for _ in xrange(5):
                tracker_under_test.insert_latest(last_deployment)
                diff = tracker_under_test.get_diff_from_hash_to_latest(
                    make_generation_hash(d))
                self.assertThat(
                    diff.apply(d),
                    Equals(last_deployment)
                )
                if last is not None:
                    self.assertThat(
                        diff,
                        Equals(last)
                    )
                last = diff

    def test_cache_runout(self):
        """
        When the cache is smaller than the number of objects that have been
        inserted into a ``GenerationTracker``, the cache runs out, and
        generation_hashes for older versions of the object start returning
        ``None`` from ``get_diff_from_hash_to_latest``.
        """
        deployments = list(deployment_strategy().example() for _ in xrange(6))
        tracker_under_test = GenerationTracker(4)
        for d in deployments:
            tracker_under_test.insert_latest(d)

        missing_diff = tracker_under_test.get_diff_from_hash_to_latest(
            make_generation_hash(deployments[0]),)
        self.assertThat(
            missing_diff,
            Is(None)
        )

        last_diff = tracker_under_test.get_diff_from_hash_to_latest(
            make_generation_hash(deployments[1]))
        self.assertThat(
            last_diff,
            Not(Is(None))
        )

        tracker_under_test.insert_latest(deployments[0])
        missing_diff = tracker_under_test.get_diff_from_hash_to_latest(
            make_generation_hash(deployments[1]))
        self.assertThat(
            missing_diff,
            Is(None)
        )
