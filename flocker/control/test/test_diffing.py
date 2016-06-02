# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.node._diffing``.
"""

from uuid import uuid4

from hypothesis import given

from .._diffing import create_diff
from .._persistence import wire_encode, wire_decode
from .._model import Node, Port
from ..testtools import (
    application_strategy,
    deployment_strategy
)

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
        deployment yields the second even after the diff has been serialized
        and re-created.
        """
        diff = create_diff(deployment_a, deployment_b)
        serialized_diff = wire_encode(diff)
        newdiff = wire_decode(serialized_diff)
        should_b_b = newdiff.apply(deployment_a)
        self.assertThat(
            should_b_b,
            Equals(deployment_b)
        )

    def test_deployment_diffing_smart(self):
        """
        Small modifications to a deployment have diffs that are small. Their
        reverse is also small.
        """
        # Any large deployment will do, just use hypothesis for convenience of
        # generating a large deployment.
        deployment = deployment_strategy(min_number_of_nodes=90).example()

        new_nodes = list(Node(uuid=uuid4()) for _ in xrange(4))
        d = reduce(lambda x, y: x.update_node(y), new_nodes, deployment)
        encoded_deployment = wire_encode(deployment)

        diff = create_diff(deployment, d)
        encoded_diff = wire_encode(diff)
        self.assertThat(
            len(encoded_diff),
            LessThan(len(encoded_deployment)/2)
        )
        self.assertThat(
            wire_decode(encoded_diff).apply(deployment),
            Equals(d)
        )

        removal_diff = create_diff(d, deployment)
        encoded_removal_diff = wire_encode(removal_diff)
        self.assertThat(
            len(encoded_removal_diff),
            LessThan(len(encoded_deployment)/2)
        )
        self.assertThat(
            wire_decode(encoded_removal_diff).apply(d),
            Equals(deployment)
        )

    def test_set_diffing_smart(self):
        """
        Small modifications to a sets have diffs that are small. Their reverse
        is also small.
        """
        # Any Application with a large set of ports will do, just use
        # hypothesis for convenience of generating a large number of ports on
        # an application.
        application = application_strategy(min_number_of_ports=1000).example()

        new_ports = list(
            Port(internal_port=i, external_port=i) for i in xrange(4)
        )
        a = reduce(
            lambda x, y: x.transform(['ports'], lambda x: x.add(y)),
            new_ports,
            application
        )
        encoded_application = wire_encode(application)

        diff = create_diff(application, a)
        encoded_diff = wire_encode(diff)
        self.assertThat(
            len(encoded_diff),
            LessThan(len(encoded_application)/2)
        )
        self.assertThat(
            wire_decode(encoded_diff).apply(application),
            Equals(a)
        )

        removal_diff = create_diff(a, application)
        encoded_removal_diff = wire_encode(removal_diff)
        self.assertThat(
            len(encoded_removal_diff),
            LessThan(len(encoded_application)/2)
        )
        self.assertThat(
            wire_decode(encoded_removal_diff).apply(a),
            Equals(application)
        )
