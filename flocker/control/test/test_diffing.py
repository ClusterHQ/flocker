# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.node._diffing``.
"""

from json import dumps
from uuid import uuid4

from eliot.testing import capture_logging, assertHasMessage
from hypothesis import given
import hypothesis.strategies as st
from pyrsistent import PClass, field, pmap, pset, InvariantException

from .._diffing import create_diff, compose_diffs, DIFF_COMMIT_ERROR
from .._persistence import wire_encode, wire_decode
from .._model import Node, Port
from ..testtools import (
    application_strategy,
    deployment_strategy,
    node_strategy,
    related_deployments_strategy
)

from ...testtools import TestCase

from testtools.matchers import Equals, LessThan


class DiffTestObj(PClass):
    """
    Simple pyrsistent object for testing.
    """
    a = field()


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
        deployment yields the second even after the diff has been serialized
        and re-created.
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

        Create a bunch of deployments and compute the incremental diffs from
        one to the next. Compose all diffs together and apply the resulting
        diff to the first deployment. Verify that the final deployment is the
        result.
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
        Small modifications to sets have diffs that are small. Their reverse
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

    def test_equal_objects(self):
        """
        Diffing objects that are equal results in an object that is smaller
        than the object.
        """
        baseobj = frozenset(xrange(1000))
        object_a = DiffTestObj(a=baseobj)
        object_b = DiffTestObj(a=baseobj)
        diff = create_diff(object_a, object_b)
        serialized_diff = wire_encode(diff)
        self.assertThat(
            len(serialized_diff),
            LessThan(len(dumps(list(baseobj))))
        )
        self.assertThat(
            wire_decode(serialized_diff).apply(object_a),
            Equals(object_b)
        )

    def test_different_objects(self):
        """
        Diffing objects that are entirely different results in a diff that can
        be applied.
        """
        object_a = DiffTestObj(a=pset(xrange(1000)))
        object_b = pmap({'1': 34})
        diff = create_diff(object_a, object_b)
        self.assertThat(
            wire_decode(wire_encode(diff)).apply(object_a),
            Equals(object_b)
        )

    def test_different_uuids(self):
        """
        Diffing objects that have parts that are simply not equal can be
        applied to turn the first object into the second.
        """
        object_a = DiffTestObj(a=uuid4())
        object_b = DiffTestObj(a=uuid4())
        diff = create_diff(object_a, object_b)

        self.assertThat(
            wire_decode(wire_encode(diff)).apply(object_a),
            Equals(object_b)
        )


class DiffTestObjInvariant(PClass):
    """
    Simple pyrsistent object with an invariant.
    """
    _perform_invariant_check = True
    a = field()
    b = field()

    def __invariant__(self):
        if self._perform_invariant_check and self.a == self.b:
            return (False, "a must not equal b")
        else:
            return (True, "")


class InvariantDiffTests(TestCase):
    """
    Tests for creating and applying diffs to objects with invariant checks.
    """
    def test_straight_swap(self):
        """
        A diff composed of two separate ``set`` operations can be applied to an
        object without triggering an invariant exception.
        """
        o1 = DiffTestObjInvariant(
            a=1,
            b=2,
        )
        o2 = DiffTestObjInvariant(
            a=2,
            b=1,
        )
        diff = create_diff(o1, o2)
        self.assertEqual(2, len(diff.changes))
        self.assertEqual(
            o2,
            diff.apply(o1)
        )

    def test_deep_swap(self):
        """
        A diff composed of two separate ``set`` operations can be applied to a
        nested object without triggering an invariant exception.
        """
        a = DiffTestObjInvariant(
            a=1,
            b=2,
        )
        b = DiffTestObjInvariant(
            a=3,
            b=4,
        )
        o1 = DiffTestObjInvariant(
            a=a,
            b=b,
        )
        o2 = o1.transform(
            ['a'],
            lambda o: o.evolver().set('a', 2).set('b', 1).persistent()
        )
        diff = create_diff(o1, o2)

        self.assertEqual(
            o2,
            diff.apply(o1)
        )

    @capture_logging(assertHasMessage, DIFF_COMMIT_ERROR)
    def test_error_logging(self, logger):
        """
        Failures while applying a diff emit a log message containing the full
        diff.
        """
        o1 = DiffTestObjInvariant(
            a=1,
            b=2,
        )
        DiffTestObjInvariant._perform_invariant_check = False
        o2 = o1.set('b', 1)
        DiffTestObjInvariant._perform_invariant_check = True
        diff = create_diff(o1, o2)
        self.assertRaises(
            InvariantException,
            diff.apply,
            o1,
        )

    def test_application_add(self):
        """
        A diff on a Node, which *adds* and application with a volume *and* the
        manifestation for the volume, can be applied without triggering an
        invariant error on the Node.
        """
        node2 = node_strategy(min_number_of_applications=1).example()
        application = node2.applications.values()[0]
        node1 = node2.transform(
            ['applications'],
            lambda o: o.remove(application.name)
        ).transform(
            ['manifestations'],
            lambda o: o.remove(application.volume.manifestation.dataset_id)
        )
        diff = create_diff(node1, node2)
        self.assertEqual(
            node2,
            diff.apply(node1),
        )

    def test_application_modify(self):
        """
        A diff on a Node, which adds a volume to an *existing* application
        volume *and* the manifestation for the volume, can be applied without
        triggering an invariant error on the Node.
        """
        node2 = node_strategy(min_number_of_applications=1).example()
        application = node2.applications.values()[0]
        volume = application.volume
        node1 = node2.transform(
            ['applications', application.name],
            lambda o: o.set('volume', None)
        ).transform(
            ['manifestations'],
            lambda o: o.remove(volume.manifestation.dataset_id)
        )
        diff = create_diff(node1, node2)
        self.assertEqual(
            node2,
            diff.apply(node1),
        )
