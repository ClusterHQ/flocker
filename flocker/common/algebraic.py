# -*- test-case-name: flocker.common.test.test_algebraic -*-
# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Invariants for algebraic data types.
"""

from pyrsistent import PClass, field

from hypothesis.strategies import sampled_from, fixed_dictionaries, just

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

    def _get_attrs(self, tag):
        return {
            attribute
            for attribute, tags in self.expected_attributes.items()
            if tag in tags
        }

    def _get_states(self, attr):
        return self.expected_attributes[attr]

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


def tagged_union_strategy(type, attr_strategies):
    invariant = type.__invariant__

    def build(tag):
        args = {
            'state': just(tag),
        }
        args.update({
            attribute: strategy
            for attribute, strategy in attr_strategies.items()
            if attribute in invariant._get_attrs(tag)
        })
        return fixed_dictionaries(args).map(lambda kwargs: type(**kwargs))

    return sampled_from(type.__invariant__.allowed_states).flatmap(build)
