# -*- test-case-name: flocker.common.test.test_algebraic -*-
# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.common.algebraic``
"""

from pyrsistent import (
    PClass, field, pset,
    InvariantException,
)
from hypothesis import given, strategies as st, assume, example

from twisted.trial.unittest import SynchronousTestCase

from twisted.python.constants import Names, NamedConstant


from ..algebraic import (
    TaggedUnionInvariant, tagged_union_strategy, merge_tagged_unions
)


class States(Names):
    ALLOWED = NamedConstant()
    WITH_ATTRIBUTE = NamedConstant()
    WITH_TWO_ATTRIBUTES = NamedConstant()
    DISALLOWED = NamedConstant()


class AlgebraicType(PClass):
    state = field(mandatory=True)
    one = field(bool)
    two = field(bool)
    extra = field(bool, mandatory=True)

    __invariant__ = TaggedUnionInvariant(
        tag_attribute='state',
        attributes_for_tag={
            States.ALLOWED: set(),
            States.WITH_ATTRIBUTE: {'one'},
            States.WITH_TWO_ATTRIBUTES: {'one', 'two'},
        },
    )

ALGEBRAIC_TYPE_STRATEGY = tagged_union_strategy(AlgebraicType, {
    'one': st.booleans(),
    'two': st.booleans(),
    'extra': st.booleans(),
})

ALGEBRAIC_TYPE_ARGUMENTS_STRATEGY = ALGEBRAIC_TYPE_STRATEGY.map(
    lambda v: v.serialize())


class TaggedUnionInvariantTests(SynchronousTestCase):
    """
    Tests for ``TaggedUnionInvariant``.
    """

    @given(
        args=ALGEBRAIC_TYPE_ARGUMENTS_STRATEGY,
    )
    @example(args={'state': States.ALLOWED, 'extra': False})
    @example(args={'state': States.WITH_ATTRIBUTE, 'extra': True, 'one': True})
    @example(args={'state': States.WITH_TWO_ATTRIBUTES,
                   'extra': True, 'one': True, 'two': False})
    def test_valid_strategy(self, args):
        """
        When a valid dictionary of attributes is provided, an
        instance of ``AlgebraicType`` is provided.
        """
        self.assertIsInstance(AlgebraicType(**args), AlgebraicType)

    @given(
        args=ALGEBRAIC_TYPE_ARGUMENTS_STRATEGY,
        choice=st.choices(),
        extra_value=st.booleans()
    )
    @example(
        args={'state': States.ALLOWED, 'extra': False},
        # The argument to add.
        choice=lambda _: 'one',
        extra_value=True,
    )
    @example(
        args={'state': States.WITH_ATTRIBUTE, 'extra': False, 'one': True},
        # The argument to add.
        choice=lambda _: 'two',
        extra_value=True,
    )
    def test_extra_attributes(self, args, choice, extra_value):
        """
        When an extra attribute that isn't allowed in a given state
        is provided, ``InvariantException`` is raised.

        :param choice: A choice function
        :param extra_value: A value to provide to the exta attribute
        """
        state = args['state']
        invariant = AlgebraicType.__invariant__
        extra_attributes = (
            invariant._all_attributes
            - invariant.attributes_for_tag[state]
        )
        assume(extra_attributes)
        extra_attribute = choice(sorted(extra_attributes))

        # Add the extra attribute to the arguments.
        args[extra_attribute] = extra_value

        exc = self.assertRaises(InvariantException, AlgebraicType, **args)
        self.assertIn(
            "can't be specified in state",
            exc.invariant_errors[0],
        )

    @given(
        args=ALGEBRAIC_TYPE_ARGUMENTS_STRATEGY,
        choice=st.choices(),
    )
    @example(
        args={'state': States.WITH_ATTRIBUTE, 'extra': False, 'one': True},
        # The argument to remove
        choice=lambda _: 'one',
    )
    @example(
        args={'state': States.WITH_TWO_ATTRIBUTES,
              'extra': False, 'one': True, 'two': False},
        # The argument to remove
        choice=lambda _: 'one',
    )
    @example(
        args={'state': States.WITH_TWO_ATTRIBUTES,
              'extra': False, 'one': True, 'two': False},
        # The argument to remove
        choice=lambda _: 'two',
    )
    def test_missing_attributes(self, args, choice):
        """
        When an attribute required in a given state isn't provided,
        ``InvariantException`` is raised.

        :param args: A valid dict of attributes for ``AlgebraicType``.
        :param choice: A choice function
        """
        state = args['state']
        invariant = AlgebraicType.__invariant__
        # The required attributes of the current state.
        required_attributes = invariant.attributes_for_tag[state]
        assume(required_attributes)
        removed_attribute = choice(sorted(required_attributes))

        # Remove a required attribute.
        del args[removed_attribute]

        exc = self.assertRaises(InvariantException, AlgebraicType, **args)
        self.assertIn(
            'must be specified in state',
            exc.invariant_errors[0],
        )

    @given(
        state=st.sampled_from(
            pset(States.iterconstants())
            - AlgebraicType.__invariant__._allowed_tags
        ),
        extra_value=st.booleans(),
    )
    @example(
        state=States.DISALLOWED,
        extra_value=False,
    )
    def test_invalid_states(self, state, extra_value):
        """
        When constructed with a state that isn't allowed,
        `InvariantException` is raised.

        :param state: A state which isn't a valid state for
            ``AlgebraicType``.
        """
        args = {'state': state, 'extra': extra_value}

        exc = self.assertRaises(InvariantException, AlgebraicType, **args)

        self.assertIn(
            'can only be in states',
            exc.invariant_errors[0],
        )


class MergeTaggedUnionsTests(SynchronousTestCase):
    """
    Tests for merge_tagged_unions.
    """

    def test_simple_merge(self):
        """
        Merging takes all attributes form the src.
        """
        src = AlgebraicType(state=States.WITH_ATTRIBUTE,
                            extra=False,
                            one=False)

        target = AlgebraicType(state=States.WITH_TWO_ATTRIBUTES,
                               extra=True,
                               one=True,
                               two=True)

        self.assertEqual(merge_tagged_unions(AlgebraicType, src, target),
                         AlgebraicType(state=States.WITH_TWO_ATTRIBUTES,
                                       extra=False,
                                       one=False,
                                       two=True))

    def test_subset_merge(self):
        """
        Merging only takes fields in the target from the source.
        """
        target  = AlgebraicType(state=States.WITH_ATTRIBUTE,
                                extra=False,
                                one=False)

        src = AlgebraicType(state=States.WITH_TWO_ATTRIBUTES,
                            extra=True,
                            one=True,
                            two=True)

        self.assertEqual(merge_tagged_unions(AlgebraicType, src, target),
                         AlgebraicType(state=States.WITH_ATTRIBUTE,
                                       extra=True,
                                       one=True))
