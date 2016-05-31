# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.node._diffing``.
"""

from os import getcwd
from uuid import uuid4
from cProfile import Profile

from hypothesis import given
import hypothesis.strategies as st

from .._diffing import create_diff, compose_diffs
from .._persistence import wire_encode, wire_decode
from .._model import Node, Port
from ..testtools import (
    application_strategy,
    deployment_strategy,
    related_deployments_strategy
)

from ...testtools import TestCase

from twisted.python.filepath import FilePath

from testtools.matchers import Equals, LessThan


def enable_profiling(profile=None):
    """
    Enable profiling of a Flocker service.

    :param profile: A ``cProfile.Profile`` object for a Flocker service.
    :param int signal: See ``signal.signal``.
    :param frame: None or frame object. See ``signal.signal``.
    """
    if profile is None:
        profile = Profile()
    profile.enable()
    return profile


def disable_profiling(profile):
    """
    Disable profiling of a Flocker service.
    Dump profiling statistics to a file.

    :param profile: A ``cProfile.Profile`` object for a Flocker service.
    :param str service: Name of or identifier for a Flocker service.
    :param int signal: See ``signal.signal``.
    :param frame: None or frame object. See ``signal.signal``.
    """
    path = FilePath(getcwd())
    path = path.child('profile')
    # This dumps the current profiling statistics and disables the
    # collection of profiling data. When the profiler is next enabled
    # the new statistics are added to existing data.
    profile.dump_stats(path.path)


class DeploymentDiffTest(TestCase):
    """
    Tests for creating and applying diffs between deployments.
    """

    @given(
        related_deployments_strategy(2)
    )
    def test_deployment_diffing(self, deployments):
        """
        Diffing two arbitrary deployments, then applying the diff to the first
        deployment yields the second.
        """
        deployment_a, deployment_b = deployments
        diff = create_diff(deployment_a, deployment_b)
        serialized_diff = wire_encode(diff)
        newdiff = wire_decode(serialized_diff)
        should_b_b = newdiff.apply(deployment_a)
        self.assertThat(
            should_b_b,
            Equals(deployment_b)
        )

    @given(
        st.lists(deployment_strategy(), min_size=3, max_size=10)
    )
    def test_deployment_diffing_composable(self, deployments):
        """
        Diffs should compose to create an aggregate diff.
        """
        reserialize = lambda x: wire_decode(wire_encode(x))
        deployment_diffs = list(
            reserialize(create_diff(a, b))
            for a, b in zip(deployments[:-1], deployments[1:])
        )
        full_diff = reserialize(compose_diffs(deployment_diffs))
        self.assertThat(
            full_diff.apply(deployments[0]),
            Equals(deployments[-1])
        )

    def test_deployment_diffing_smart(self):
        """
        Small modifications to a deployment have diffs that are small.
        """
        # Any large deployment will do, just use hypothesis for convenience of
        # generating a large deployment.
        p = enable_profiling()
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
        disable_profiling(p)

    def test_set_diffing_smart(self):
        """
        Small modifications to a sets have diffs that are small.
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
