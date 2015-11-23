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
    :param dict attributes_for_tag: Dictionary mapping states to the
        set of attributes allowed in that state.
    """

    tag_attribute = field(str, mandatory=True)
    attributes_for_tag = field(dict, mandatory=True)

    @property
    def _allowed_tags(self):
        return set(self.attributes_for_tag.keys())

    @property
    def _all_attributes(self):
        return {
            attribute
            for tag, attributes in self.attributes_for_tag.items()
            for attribute in attributes
        }

    def __call__(self, value):
        tag = getattr(value, self.tag_attribute)
        if tag not in self._allowed_tags:
            return (False, "can only be in {tag_name}s {tags}.".format(
                tag_name=self.tag_attribute,
                tags=', '.join(map("`{0.name}`".format,
                                   self._allowed_tags)),
            ))
        for attribute in self.attributes_for_tag[tag]:
            if not hasattr(value, attribute):
                return (
                    False,
                    "`{attr}` must be specified in {tag_name} `{tag}`"
                    .format(attr=attribute,
                            tag_name=self.tag_attribute,
                            tag=tag.name))
        for attribute in self._all_attributes - self.attributes_for_tag[tag]:
            if hasattr(value, attribute):
                return (
                    False,
                    "`{attr}` can't be specified in {tag_name} `{tag}`"
                    .format(attr=attribute,
                            tag_name=self.tag_attribute,
                            tag=tag.name))
        return (True, "")


def tagged_union_strategy(type, attr_strategies):
    """
    Create a strategy for building a type with a ``TaggedUnionInvariant``.

    :param type: Type to generate a strategy for.
    :param attr_strategies: Mapping of attributes to stratgeies to
        dgenerate corresponding attributes.
    :type attr_strategies: ``dict`` mapping ``str`` to ``SearchStrategy`s.
    """
    invariant = type.__invariant__

    def build(tag):
        args = {
            invariant.tag_attribute: just(tag),
        }
        args.update({
            attribute: strategy
            for attribute, strategy in attr_strategies.items()
            if attribute in invariant.attributes_for_tag[tag]
            or attribute not in invariant._all_attributes
        })
        return fixed_dictionaries(args).map(lambda kwargs: type(**kwargs))

    return sampled_from(invariant._allowed_tags).flatmap(build)
