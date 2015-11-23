# -*- test-case-name: flocker.common.test.test_algebraic -*-
# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Invariants for algebraic data types.

This currently provides an invariant for defining a tagged union. For
example, a volume can either be detached, attached (with an
associated block device) or mounted (with an associated block device
and mount point). The invariant ensures that all and only the
appropriate attributes are set in each state.

.. code::

    class VolumeStates(Names):
       # Not attached
       DEATTACHED = NamedConstant()
       # Attached to this node but no filesystem
       ATTACHED_NO_FILESYSTEM = NamedConstant()
       # Attached to this node, has filesystem
       ATTACHED = NamedConstant()
       # Mounted on this node
       MOUNTED = NamedConstant()

   class Dataset(PClass):
       state = field(mandatory=True)
       dataset_id = field(type=UUID, mandatory=True)
       device_path = field(FilePath)
       mount_point = field(FilePath)

       __invariant__ = TaggedUnionInvariant(
           tag_attribute='state',
           attributes_for_tag={
               DatasetStates.DETACHED: set(),
               DatasetStates.ATTACHED_NO_FILESYSTEM: {'device_path'},
               DatasetStates.ATTACHED: {'device_path'},
               DatasetStates.MOUNTED: {'device_path', 'mount_point'},
           },
       )
"""

from pyrsistent import PClass, field

from hypothesis.strategies import sampled_from, fixed_dictionaries, just

__all__ = ["TaggedUnionInvariant"]


class TaggedUnionInvariant(PClass):
    """
    An invariant that ensure the given object has an allowd tag
    attribute, and that all the other specified attributes are
    present if and only if the object has the appropriate tag.

    Note: Attributes that aren't specified by any tag are ignored.

    :param str tag_attribute: The attribute that contains the tag.
    :param dict attributes_for_tag: Dictionary mapping tags to the
        set of attributes allowed by that tag.
    """

    tag_attribute = field(str, mandatory=True)
    attributes_for_tag = field(dict, mandatory=True)

    @property
    def _allowed_tags(self):
        """
        The set of all allowed tags.
        """
        return set(self.attributes_for_tag.keys())

    @property
    def _all_attributes(self):
        """
        The set of all attributes controlled by the invariant.
        """
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
