# -*- test-case-name: flocker.common.test.test_algebraic -*-
# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

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


from ..algebraic import StateInvariant


class States(Names):
    ALLOWED = NamedConstant()
    WITH_ATTRIBUTE = NamedConstant()
    WITH_TWO_ATTRIBUTES = NamedConstant()
    DISALLOWED = NamedConstant()


class AlgebraicType(PClass):
    state = field(mandatory=True)
    one = field(bool)
    two = field(bool)

    __invariant__ = StateInvariant(
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

ARGS_STRATEGEY = st.fixed_dictionaries({
    'state': st.sampled_from(AlgebraicType.__invariant__.allowed_states),
    'one': st.booleans(),
    'two': st.booleans(),
})


class MakeStateInvariantTests(SynchronousTestCase):

    @given(
        args=ARGS_STRATEGEY,
        extra_attribute=st.sampled_from(
            AlgebraicType.__invariant__.expected_attributes
        ),
    )
    def test_extra_attributes(self, args, extra_attribute):
        for attribute, states in (
                AlgebraicType.__invariant__.expected_attributes.items()
        ):
            if attribute == extra_attribute:
                assume(args['state'] not in states)
                continue
            if args['state'] not in states:
                del args[attribute]
        exc = self.assertRaises(InvariantException, AlgebraicType, **args)
        self.assertIn(
            'can only be specified in state',
            exc.invariant_errors[0],
        )

    @given(
        args=ARGS_STRATEGEY,
        missing_attribute=st.sampled_from(
            AlgebraicType.__invariant__.expected_attributes
        ),
    )
    def test_missing_attributes(self, args, missing_attribute):
        for attribute, states in (
            AlgebraicType.__invariant__.expected_attributes.items()
        ):
            if attribute == missing_attribute:
                assume(args['state'] in states)
                del args[attribute]
            if args['state'] not in states:
                del args[attribute]
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
        args=ARGS_STRATEGEY,
    )
    def test_invalid_states(self, state, args):
        """
        When constructed with a state that isn't allowed,
        """
        args['state'] = state
        for attribute in (
            AlgebraicType.__invariant__.expected_attributes.keys()
        ):
            del args[attribute]
        exc = self.assertRaises(InvariantException, AlgebraicType, **args)
        self.assertIn(
            'can only be in states',
            exc.invariant_errors[0],
        )
