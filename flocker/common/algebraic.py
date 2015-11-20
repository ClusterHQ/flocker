# -*- test-case-name: flocker.common.test.test_algebraic -*-
# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Invariants for algebraic data types.
"""

from pyrsistent import PClass, field

__all__ = ["TaggedUnionInvariant"]


class TaggedUnionInvariant(PClass):
    """
    An invariant that ensure the given object has a ``state`` attribute
    in the given states, and that all the other specified attributes are
    present if and only if the object is in one of the corresponding states.

    :param set allowed_states: Set of allowed states.
    :param dict expected_attributes: Dictionary mapping attribute names to
        the set of states that attribute should be present in.
    """

    allowed_states = field(set, mandatory=True)
    expected_attributes = field(dict, mandatory=True)

    def __call__(self, value):
        for attribute, states in self.expected_attributes.items():
            if (value.state in states) != hasattr(value, attribute):
                if value.state in states:
                    message = (
                        "`{attr}` must be specified in state `{state}`"
                        .format(attr=attribute, state=value.state.name)
                    )
                else:
                    message = (
                        "`{attr}` can only be specified in states {states}"
                        .format(
                            attr=attribute,
                            states=', '.join(map("`{0.name}`".format, states)),
                        )
                    )
                return (False, message)
        if value.state not in self.allowed_states:
            return (False, "can only be in states {states}.".format(
                states=', '.join(map("`{0.name}`".format,
                                     self.allowed_states)),
            ))
        return (True, "")
