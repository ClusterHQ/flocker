# -*- test-case-name: flocker.common.test.test_algebraic -*-
# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``flocker.common.algebraic``
"""

from pyrsistent import (
    PClass, field,
    InvariantException,
)
from hypothesis import given, strategies as st, assume

from twisted.trial.unittest import SynchronousTestCase

from twisted.python.constants import Names, NamedConstant


from ..algebraic import TaggedUnionInvariant, tagged_union_strategy


class States(Names):
    ALLOWED = NamedConstant()
    WITH_ATTRIBUTE = NamedConstant()
    WITH_TWO_ATTRIBUTES = NamedConstant()
    DISALLOWED = NamedConstant()


class AlgebraicType(PClass):
    state = field(mandatory=True)
    one = field(bool)
    two = field(bool)

    __invariant__ = TaggedUnionInvariant(
        allowed_states={
            States.ALLOWED,
            States.WITH_ATTRIBUTE,
            States.WITH_TWO_ATTRIBUTES,
        },
        expected_attributes={
            'one': {States.WITH_ATTRIBUTE, States.WITH_TWO_ATTRIBUTES},
            'two': {States.WITH_TWO_ATTRIBUTES},
        },
    )

ALGEBRAIC_TYPE_STRATEGY = tagged_union_strategy(AlgebraicType, {
    'one': st.booleans(),
    'two': st.booleans(),
})

ALGEBRAIC_TYPE_ARGUMENTS_STRATGEY = ALGEBRAIC_TYPE_STRATEGY.map(
    lambda v: v.serialize())


class MakeTaggedUnionInvariantTests(SynchronousTestCase):

    @given(
        args=ALGEBRAIC_TYPE_ARGUMENTS_STRATGEY,
    )
    def test_valid_strategy(self, args):
        """
        When a valid dictionary of attributes is provided, an
        instance of ``AlgebraicType`` is provided.
        """
        self.assertIsInstance(AlgebraicType(**args), AlgebraicType)

    @given(
        args=ALGEBRAIC_TYPE_ARGUMENTS_STRATGEY,
        choice=st.choices(),
        extra_value=st.booleans()
    )
    def test_extra_attributes(self, args, choice, extra_value):
        """
        When an extra attribute that isn't allowed in a given state
        is provided, ``InvariantException`` is raised.

        :param choice: A choice function
        :param extra_value: A value to provide to the exta attribute
        """
        state = args['state']
        extra_attributes = (
            set(AlgebraicType.__invariant__.expected_attributes.keys())
            - AlgebraicType.__invariant__._get_attrs(state)
        )
        assume(extra_attributes)
        extra_attribute = choice(sorted(extra_attributes))

        # Add the extra attribute to the arguments.
        args[extra_attribute] = extra_value

        exc = self.assertRaises(InvariantException, AlgebraicType, **args)
        self.assertIn(
            'can only be specified in state',
            exc.invariant_errors[0],
        )

    @given(
        args=ALGEBRAIC_TYPE_ARGUMENTS_STRATGEY,
        choice=st.choices(),
    )
    def test_missing_attributes(self, args, choice):
        """
        When an attribute required in a given state isn't provided,
        ``InvariantException`` is raised.

        :param args: A valid dict of attributes for ``AlgebraicType``.
        :param choice: A choice function
        """
        state = args['state']
        # The required attributes of the current state.
        required_attributes = AlgebraicType.__invariant__._get_attrs(state)
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
            set(States.iterconstants())
            - AlgebraicType.__invariant__.allowed_states
        ),
    )
    def test_invalid_states(self, state):
        """
        When constructed with a state that isn't allowed,
        `InvariantException` is raised.

        :param state: A state which isn't a valid state for
            ``AlgebraicType``.
        """
        args = {'state': state}

        exc = self.assertRaises(InvariantException, AlgebraicType, **args)

        self.assertIn(
            'can only be in states',
            exc.invariant_errors[0],
        )
