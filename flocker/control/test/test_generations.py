# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.node._generations``.
"""

from testtools.matchers import Equals, Is, Not, HasLength

from ...testtools import TestCase

from ..testtools import related_deployments_strategy
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
        deployments = related_deployments_strategy(5).example()

        # The diffing algorithm is potentially a little more interesting if
        # there are repeat deployments in the queue of deployments being
        # tracked.
        deployments[3] = deployments[1]

        tracker_under_test = GenerationTracker(10)
        # Populate the queue of deployment configurations in the tracker with
        # each of the generated deployments.
        for d in deployments:
            tracker_under_test.insert_latest(d)

        # The latest deployment is the last one added.
        last_deployment = deployments[-1]

        # Verify that we can compute the diff from each of the deployments to
        # the latest deployment.
        for d in deployments:
            computed_diffs = set()

            for _ in xrange(5):
                # In practice, we might insert the last deployment multiple
                # times. Verify that no matter how many times we insert it, we
                # still compute a valid diff.
                tracker_under_test.insert_latest(last_deployment)

                diff = tracker_under_test.get_diff_from_hash_to_latest(
                    make_generation_hash(d))

                # Verify that the returned diff can be applied to the current
                # deployment to transform it into the latest deployment.
                self.assertThat(
                    diff.apply(d),
                    Equals(last_deployment)
                )
                computed_diffs.append(diff)

            # Verify that all of the diffs that we computed were the same.
            self.assertThat(
                computed_diffs,
                HasLength(1)
            )

    def test_cache_runout(self):
        """
        When the cache is smaller than the number of objects that have been
        inserted into a ``GenerationTracker``, the cache runs out, and
        generation_hashes for older versions of the object start returning
        ``None`` from ``get_diff_from_hash_to_latest``.
        """
        deployments = related_deployments_strategy(6)
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
