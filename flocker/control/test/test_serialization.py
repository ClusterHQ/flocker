# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.control._serialization``.
"""
from datetime import datetime, timedelta
import json
from uuid import uuid4

from hypothesis import given
from hypothesis import strategies as st
from pyrsistent import PClass
from pytz import UTC
from testtools.matchers import Is, Equals, Not
from twisted.python.filepath import FilePath

from ..testtools import deployment_strategy

from .._serialization import (
    wire_encode,
    wire_decode,
    to_unserialized_json,
    SERIALIZABLE_CLASSES,
    generation_hash,
)

from .._model import NodeState
from ...testtools import TestCase
from .test_persistence import (
    LATEST_TEST_DEPLOYMENT,
    DEPLOYMENTS,
    TEST_DEPLOYMENT_1,
    TEST_DEPLOYMENT_2,
)


class WireEncodeDecodeTests(TestCase):
    """
    Tests for ``to_unserialized_json``, ``wire_encode`` and ``wire_decode``.
    """
    def test_encode_to_bytes(self):
        """
        ``wire_encode`` converts the given object to ``bytes``.
        """
        self.assertIsInstance(wire_encode(LATEST_TEST_DEPLOYMENT), bytes)

    @given(DEPLOYMENTS)
    def test_roundtrip(self, deployment):
        """
        A range of generated configurations (deployments) can be
        roundtripped via the wire encode/decode.
        """
        source_json = wire_encode(deployment)
        decoded_deployment = wire_decode(source_json)
        self.assertEqual(decoded_deployment, deployment)

    @given(DEPLOYMENTS)
    def test_to_unserialized_json(self, deployment):
        """
        ``to_unserialized_json`` is same output as ``wire_encode`` except
        without doing JSON byte encoding.
        """
        unserialized = to_unserialized_json(deployment)
        self.assertEquals(wire_decode(json.dumps(unserialized)), deployment)

    def test_no_arbitrary_decoding(self):
        """
        ``wire_decode`` will not decode classes that are not in
        ``SERIALIZABLE_CLASSES``.
        """
        class Temp(PClass):
            """A class."""
        SERIALIZABLE_CLASSES.append(Temp)

        def cleanup():
            if Temp in SERIALIZABLE_CLASSES:
                SERIALIZABLE_CLASSES.remove(Temp)
        self.addCleanup(cleanup)

        data = wire_encode(Temp())
        SERIALIZABLE_CLASSES.remove(Temp)
        # Possibly future versions might throw exception, the key point is
        # that the returned object is not a Temp instance.
        self.assertFalse(isinstance(wire_decode(data), Temp))

    def test_complex_keys(self):
        """
        Objects with attributes that are ``PMap``\s with complex keys
        (i.e. not strings) can be roundtripped.
        """
        node_state = NodeState(hostname=u'127.0.0.1', uuid=uuid4(),
                               manifestations={}, paths={},
                               devices={uuid4(): FilePath(b"/tmp")})
        self.assertEqual(node_state, wire_decode(wire_encode(node_state)))

    def test_datetime(self):
        """
        A datetime with a timezone can be roundtripped (with potential loss of
        less-than-second resolution).
        """
        dt = datetime.now(tz=UTC)
        self.assertTrue(
            abs(wire_decode(wire_encode(dt)) - dt) < timedelta(seconds=1))

    def test_naive_datetime(self):
        """
        A naive datetime will fail. Don't use those, always use an explicit
        timezone.
        """
        self.assertRaises(ValueError, wire_encode, datetime.now())


class GenerationHashTests(TestCase):
    """
    Tests for generation_hash.
    """

    @given(st.data())
    def test_no_hash_collisions(self, data):
        """
        Hashes of different deployments do not have hash collisions, hashes of
        the same object have the same hash.
        """
        # With 128 bits of hash, a collision here indicates a fault in the
        # algorithm.

        # Generate the first deployment.
        deployment_a = data.draw(deployment_strategy())

        # Decide if we want to generate a second deployment, or just compare
        # the first deployment to a re-serialized version of itself:
        simple_comparison = data.draw(st.booleans())
        if simple_comparison:
            deployment_b = wire_decode(wire_encode(deployment_a))
        else:
            deployment_b = data.draw(deployment_strategy())

        should_be_equal = (deployment_a == deployment_b)
        if simple_comparison:
            self.assertThat(
                should_be_equal,
                Is(True)
            )

        hash_a = generation_hash(deployment_a)
        hash_b = generation_hash(deployment_b)

        if should_be_equal:
            self.assertThat(
                hash_a,
                Equals(hash_b)
            )
        else:
            self.assertThat(
                hash_a,
                Not(Equals(hash_b))
            )

    def test_maps_and_sets_differ(self):
        """
        Mappings hash to different values than frozensets of their iteritems().
        """
        self.assertThat(
            generation_hash(frozenset([('a', 1), ('b', 2)])),
            Not(Equals(generation_hash(dict(a=1, b=2))))
        )

    def test_strings_and_jsonable_types_differ(self):
        """
        Strings and integers hash to different values.
        """
        self.assertThat(
            generation_hash(5),
            Not(Equals(generation_hash('5')))
        )

    def test_sets_and_objects_differ(self):
        """
        Sets can be hashed and 1 element sets have a different hash than the
        hash of the single element.
        """
        self.assertThat(
            generation_hash(5),
            Not(Equals(generation_hash(frozenset([5]))))
        )

    def test_lists_and_objects_differ(self):
        """
        Lists can be hashed, and have a different hash value than scalars with
        the same value or sets with the same values.
        """
        self.assertThat(
            generation_hash(913),
            Not(Equals(generation_hash([913])))
        )
        self.assertThat(
            generation_hash(frozenset([913])),
            Not(Equals(generation_hash([913])))
        )

    def test_empty_sets_can_be_hashed(self):
        """
        Empty sets can be hashed and result in different hashes than empty
        strings or the string 'NULLSET'.
        """
        self.assertThat(
            generation_hash(frozenset()),
            Not(Equals(generation_hash('')))
        )
        self.assertThat(
            generation_hash(frozenset()),
            Not(Equals(generation_hash(b'NULLSET')))
        )

    def test_unicode_hash(self):
        """
        Unicode strings can be hashed, and are hashed to the same value as
        their bytes equivalent.
        """
        self.assertThat(
            generation_hash(unicode(u'abcde')),
            Equals(generation_hash(bytes(b'abcde')))
        )

    def test_consistent_hash(self):
        """
        A given deployment hashes to a specific value.
        """
        # Unfortunately these are manually created golden values generated by
        # running the test with wrong values and copying the output into this
        # file. This test mostly adds value in verifying that the hashes
        # computed in all of our CI environments are the same.
        TEST_DEPLOYMENT_1_HASH = ''.join(chr(x) for x in [
            0x4e, 0x35, 0x2b, 0xa2, 0x68, 0xde, 0x10, 0x0a,
            0xa5, 0xbc, 0x8a, 0x7e, 0x75, 0xc7, 0xf4, 0xe6
        ])
        TEST_DEPLOYMENT_2_HASH = ''.join(chr(x) for x in [
            0x96, 0xe6, 0xcb, 0xa9, 0x5f, 0x7c, 0x8e, 0xfa,
            0xf8, 0x76, 0x8a, 0xc6, 0x89, 0x1a, 0xec, 0xc5
        ])
        self.assertThat(
            generation_hash(TEST_DEPLOYMENT_1),
            Equals(TEST_DEPLOYMENT_1_HASH)
        )
        self.assertThat(
            generation_hash(TEST_DEPLOYMENT_2),
            Equals(TEST_DEPLOYMENT_2_HASH)
        )
