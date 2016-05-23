# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.node._diffing``.
"""

from uuid import uuid4

from hypothesis import given

from .._diffing import create_deployment_diff
from .._persistence import wire_encode, wire_decode
from .._model import Node
from ..testtools import deployment_strategy

from ...testtools import TestCase

from testtools.matchers import Equals, LessThan


class DeploymentDiffTest(TestCase):
    """
    Tests for creating and applying diffs between deployments.
    """

    @given(
        deployment_strategy(),
        deployment_strategy(),
    )
    def test_deployment_diffing(self, deployment_a, deployment_b):
        """
        Diffing two arbitrary deployments, then applying the diff to the first
        deployment yields the second.
        """
        diff = create_deployment_diff(deployment_a, deployment_b)
        serialized_diff = wire_encode(diff)
        newdiff = wire_decode(serialized_diff)
        should_b_b = newdiff.apply(deployment_a)
        self.assertThat(
            should_b_b,
            Equals(deployment_b)
        )

    def test_deployment_diffing_smart(self):
        """
        Small modifications to a deployment have diffs that are small.
        """
        # Any large deployment will do, just use hypothesis for convenience of
        # generating a large deployment.
        deployment = deployment_strategy(min_number_of_nodes=900).example()

        new_nodes = list(Node(uuid=uuid4()) for _ in xrange(4))
        d = reduce(lambda x, y: x.update_node(y), new_nodes, deployment)
        encoded_deployment = wire_encode(deployment)

        diff = create_deployment_diff(deployment, d)
        encoded_diff = wire_encode(diff)
        self.assertThat(
            len(encoded_diff),
            LessThan(len(encoded_deployment)/2)
        )

        removal_diff = create_deployment_diff(d, deployment)
        encoded_removal_diff = wire_encode(removal_diff)
        self.assertThat(
            len(encoded_removal_diff),
            LessThan(len(encoded_deployment)/2)
        )
