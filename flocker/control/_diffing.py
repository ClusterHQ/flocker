# Copyright ClusterHQ Inc.  See LICENSE file for details.
# -*- test-case-name: flocker.control.test.test_diffing -*-

"""
Code to calculate the difference between objects. This is particularly useful
for computing the difference between deeply pyrsisistent objects such as the
flocker configuration or the flocker state.
"""

from eliot import MessageType, Field

from pyrsistent import (
    PClass,
    PMap,
    PSet,
    field,
    pvector,
    pvector_field,
)

# XXX The _EvolverProxy (or something similar) should be provided by
# Pyrsistent, but meanwhile we'll import this useful private function.
# https://github.com/tobgu/pyrsistent/issues/89
from pyrsistent._transformations import _get

from zope.interface import Attribute, Interface, implementer, classImplements


class _IDiffChange(Interface):
    """
    Interface for a diff change.

    This is simply something that can be applied to an object to create a new
    object.

    This interface is created as documentation rather than for any of the
    actual zope.interface mechanisms.
    """

    def apply(obj):
        """
        Apply this diff change to the passed in object and return a new object
        that is obj with the ``self`` diff applied.

        :param object obj: The object to apply the diff to.

        :returns: A new object that is the passed in object with the diff
            applied.
        """


@implementer(_IDiffChange)
class _Replace(PClass):
    """
    A ``_IDiffChange`` that returns a new root object.

    :ivar value: The item to be the new root object for subsequent operations.
    """
    value = field()

    def apply(self, obj):
        return _TransformProxy(self.value)


@implementer(_IDiffChange)
class _Remove(PClass):
    """
    A ``_IDiffChange`` that removes an object from a ``PSet`` or a key from a
    ``PMap`` inside a nested object tree.

    :ivar path: The path in the nested object tree of the object to be removed
        from the import set.

    :ivar item: The item to be removed from the set or the key to be removed
        from the mapping.
    """
    path = pvector_field(object)
    item = field()

    def apply(self, obj):
        return obj.transform(self.path, lambda o: o.remove(self.item))


@implementer(_IDiffChange)
class _Set(PClass):
    """
    A ``_IDiffChange`` that sets a field in a ``PClass`` or sets a key in a
    ``PMap``.

    :ivar path: The path in the nested object which supports `set` operations.
    :ivar key: The key to set.
    :ivar value: The value to set.
    """
    path = pvector_field(object)
    key = field()
    value = field()

    def apply(self, obj):
        return obj.transform(
            self.path, lambda o: o.set(self.key, self.value)
        )


@implementer(_IDiffChange)
class _Add(PClass):
    """
    A ``_IDiffChange`` that adds an item to a ``PSet``.

    :ivar path: The path to the set to which the item will be added.

    :ivar item: The item to be added to the set.
    """
    path = pvector_field(object)
    item = field()

    def apply(self, obj):
        return obj.transform(self.path, lambda x: x.add(self.item))


_sentinel = object()


class _IEvolvable(Interface):
    """
    An interface to mark classes that provide a ``Pyrsistent`` style
    ``evolver`` method.
    """
    def evolver():
        """
        :returns: A mutable version of the underlying object.
        """

classImplements(PSet, _IEvolvable)
classImplements(PMap, _IEvolvable)
classImplements(PClass, _IEvolvable)


class _ISetType(Interface):
    """
    The operations that can be performed when transforming a ``PSet`` object.
    """
    def add(item):
        """
        Add ``item`` to set.
        """

    def remove(item):
        """
        Remove ``item`` from set.
        """

classImplements(PSet, _ISetType)


class _IRecordType(Interface):
    """
    The operations that can be performed when transforming a ``PSet`` object.
    """
    def set(key, value):
        """
        Add or replace the ``key`` in a ``PMap`` with ``value``.
        """

    def remove(item):
        """
        Remove the ``key`` in a ``PMap``.
        """

classImplements(PMap, _IRecordType)
classImplements(PClass, _IRecordType)


class _IRecursiveEvolverProxy(Interface):
    """
    An interface which allows a structure of nested ``PClass``, ``PMap``, and
    ``PSet`` to be evolved recursively.
    """
    _original = Attribute(
        "The root Pyrsistent object that is being evolved. "
        "Must provide ``_IEvolvable``"
    )
    _children = Attribute(
        "A collection of child ``_IRecursiveEvolverProxy`` objects."
    )

    def commit():
        """
        Recursively persist the structure rooted at ``_original`` starting with
        leaf nodes.

        :returns: The persisted immutable structure.
        """


@implementer(_IRecursiveEvolverProxy)
@implementer(_ISetType)
class _EvolverProxyForSet(object):
    """
    A proxy for recursively evolving a ``PSet``.
    """
    def __init__(self, original):
        """
        :param _ISetType original: See ``_IRecursiveEvolverProxy._original``.
        """
        self._original = original
        self._evolver = original.evolver()
        self._children = {}

    def add(self, item):
        """
        Add ``item`` to the ``original`` ``Pset`` or if the item is itself a
        Pyrsistent object, add a new proxy for that item so that further
        operations can be performed on it without triggering invariant checks
        until the tree is finally committed.

        :param item: An object to be added to the ``PSet`` wrapped by this
            proxy.
        :returns: ``self``
        """
        if _IEvolvable.providedBy(item):
            self._children[item] = _proxy_for_evolvable_object(item)
        else:
            self._evolver.add(item)
        return self

    def remove(self, item):
        """
        Remove the ``item`` in an evolver of the ``original`` ``PSet``, and if
        the item is an uncommitted ``_EvolverProxy`` remove it from the list of
        children so that the item is not persisted when the structure is
        finally committed.

        :param item: The object to be removed from the wrapped ``PSet``
        :returns: ``self``
        """
        self._children.pop(item, None)
        # Attempt to remove the item from the evolver too.  It may be something
        # that was replaced rather than added by a previous ``set`` operation.
        try:
            self._evolver.remove(item)
        except KeyError:
            pass
        return self

    def commit(self):
        for child_evolver_proxy in self._children.values():
            child = child_evolver_proxy.commit()
            self._evolver.add(child)
        return self._evolver.persistent()


@implementer(_IRecursiveEvolverProxy)
@implementer(_IRecordType)
class _EvolverProxyForRecord(object):
    """
    A proxy for recursively evolving a ``PMap`` or ``PClass``.
    """
    def __init__(self, original):
        """
        :param _IRecordType original: See
            ``_IRecursiveEvolverProxy._original``.
        """
        self._original = original
        self._evolver = original.evolver()
        self._children = {}

    def set(self, key, item):
        """
        Set the ``item`` in an evolver of the ``original`` ``PMap`` or
        ``PClass`` or if the item is itself a Pyrsistent object, add a new
        proxy for that item so that further operations can be performed on it
        without triggering invariant checks until the tree is finally
        committed.

        :param item: An object to be added or set on the ``PMap`` wrapped by
            this proxy.
        :returns: ``self``
        """
        if _IEvolvable.providedBy(item):
            # This will replace any existing proxy.
            self._children[key] = _proxy_for_evolvable_object(item)
        else:
            self._evolver.set(key, item)
        return self

    def remove(self, key):
        """
        Remove the ``key`` in an evolver of the ``original`` ``PMap``, or
        ``PClass`` and if the item is an uncommitted ``_EvolverProxy`` remove
        it from the list of children so that the item is not persisted when the
        structure is finally committed.

        :param key: The key to be removed from the wrapped ``PMap``
        :returns: ``self``
        """
        self._children.pop(key, None)
        # Attempt to remove the item from the evolver too.  It may be something
        # that was replaced rather than added by a previous ``set`` operation.
        try:
            self._evolver.remove(key)
        except KeyError:
            pass
        return self

    def commit(self):
        for segment, child_evolver_proxy in self._children.items():
            child = child_evolver_proxy.commit()
            self._evolver.set(segment, child)
        return self._evolver.persistent()


def _proxy_for_evolvable_object(obj):
    """
    :returns: an ``_IRecursiveEvolverProxy`` suitable for the type of ``obj``.
    """
    if not _IEvolvable.providedBy(obj):
        raise TypeError(
            "{!r} does not provide {}".format(
                obj,
                _IEvolvable.__name__
            )
        )
    if _ISetType.providedBy(obj):
        return _EvolverProxyForSet(obj)
    elif _IRecordType.providedBy(obj):
        return _EvolverProxyForRecord(obj)
    else:
        raise TypeError("Object '{}' does not provide a supported interface")


def _get_or_add_proxy_child(parent_proxy, segment):
    """
    Returns a proxy wrapper around the ``_IEvolvable`` object corresponding to
    ``segment``. A new proxy is created if one does not already exist and it is
    added to ``parent_proxy._children``.

    :param _IParentProxy parent_proxy: The parent.
    :param unicode segment: The label in a ``path`` supplied to ``transform``.
    :returns:
    """
    child = parent_proxy._children.get(segment)
    if child is not None:
        return child
    child = _get(parent_proxy._original, segment, _sentinel)
    if child is _sentinel:
        raise KeyError(
            "Attribute or key '{}' not found in {}".format(
                segment, parent_proxy._original
            )
        )
    proxy_for_child = _proxy_for_evolvable_object(child)
    parent_proxy._children[segment] = proxy_for_child
    return proxy_for_child


@implementer(_IRecursiveEvolverProxy)
class _TransformProxy(object):
    """
    This attempts to bunch a the ``transform`` operations performed when
    applying a sequence of diffs into a single transaction so that related
    attributes can be ``set`` without triggering an in invariant error.
    Leaf nodes are persisted first and in isolation, so as not to trigger
    invariant errors in ancestor nodes.
    """
    def __init__(self, original):
        """
        :param _IEvolvable original: The root object to which transformations
            will be applied.
        """
        self._root = _proxy_for_evolvable_object(original)

    def transform(self, path, operation):
        """
        Traverse each segment of ``path`` to create a hierarchy of
        ``_EvolverProxy`` objects and perform the ``operation`` on the
        resulting leaf proxy object. This will infact perform the operation on
        an evolver of the original Pyrsistent object.

        The object corresponding to the last segment of ``path`` must provide
        the ``_IEvolvable`` interface.

        :param PVector path: The path relative to ``original`` which will be
            operated on.
        :param callable operation: A function to be applied to an evolver of
             the object at ``path``
        :returns: ``self``
        """
        target = self._root
        for segment in path:
            target = _get_or_add_proxy_child(target, segment)
        operation(target)
        return self

    def commit(self):
        return self._root.commit()


TARGET_OBJECT = Field(
    u"target_object", repr,
    u"The object to which the diff was applied."
)
CHANGES = Field(
    u"changes", repr,
    u"The changes being applied."
)

DIFF_COMMIT_ERROR = MessageType(
    u"flocker:control:Diff:commit_error",
    [TARGET_OBJECT, CHANGES],
    u"The target and changes that failed to apply."
)


@implementer(_IDiffChange)
class Diff(PClass):
    """
    A ``_IDiffChange`` that is simply the serial application of other diff
    changes.

    This is the object that external modules get and use to apply diffs to
    objects.

    :ivar changes: A vector of ``_IDiffChange`` s that represent a diff between
        two objects.
    """

    changes = pvector_field(object)

    def apply(self, obj):
        proxy = _TransformProxy(original=obj)
        for c in self.changes:
            proxy = c.apply(proxy)
        try:
            return proxy.commit()
        except:
            # Imported here to avoid circular dependencies.
            from ._persistence import wire_encode
            DIFF_COMMIT_ERROR(
                target_object=wire_encode(obj),
                changes=wire_encode(self.changes),
            ).write()
            raise


def _create_diffs_for_sets(current_path, set_a, set_b):
    """
    Computes a series of ``_IDiffChange`` s to turn ``set_a`` into ``set_b``
    assuming that these sets are at ``current_path`` inside a nested pyrsistent
    object.

    :param current_path: An iterable of pyrsistent object describing the path
        inside the root pyrsistent object where the other arguments are
        located.  See ``PMap.transform`` for the format of this sort of path.

    :param set_a: The desired input set.

    :param set_b: The desired output set.

    :returns: An iterable of ``_IDiffChange`` s that will turn ``set_a`` into
        ``set_b``.
    """
    resulting_diffs = pvector([]).evolver()
    for item in set_a.difference(set_b):
        resulting_diffs.append(
            _Remove(path=current_path, item=item)
        )
    for item in set_b.difference(set_a):
        resulting_diffs.append(
            _Add(path=current_path, item=item)
        )
    return resulting_diffs.persistent()


def _create_diffs_for_mappings(current_path, mapping_a, mapping_b):
    """
    Computes a series of ``_IDiffChange`` s to turn ``mapping_a`` into
    ``mapping_b`` assuming that these mappings are at ``current_path`` inside a
    nested pyrsistent object.

    :param current_path: An iterable of pyrsistent object describing the path
        inside the root pyrsistent object where the other arguments are
        located.  See ``PMap.transform`` for the format of this sort of path.

    :param mapping_a: The desired input mapping.

    :param mapping_b: The desired output mapping.

    :returns: An iterable of ``_IDiffChange`` s that will turn ``mapping_a``
        into ``mapping_b``.
    """
    resulting_diffs = pvector([]).evolver()
    a_keys = frozenset(mapping_a.keys())
    b_keys = frozenset(mapping_b.keys())
    for key in a_keys.intersection(b_keys):
        if mapping_a[key] != mapping_b[key]:
            resulting_diffs.extend(
                _create_diffs_for(
                    current_path.append(key),
                    mapping_a[key],
                    mapping_b[key]
                )
            )
    for key in b_keys.difference(a_keys):
        resulting_diffs.append(
            _Set(path=current_path, key=key, value=mapping_b[key])
        )
    for key in a_keys.difference(b_keys):
        resulting_diffs.append(
            _Remove(path=current_path, item=key)
        )
    return resulting_diffs.persistent()


def _create_diffs_for(current_path, subobj_a, subobj_b):
    """
    Computes a series of ``_IDiffChange`` s to turn ``subobj_a`` into
    ``subobj_b`` assuming that these subobjs are at ``current_path`` inside a
    nested pyrsistent object.

    :param current_path: An iterable of pyrsistent object describing the path
        inside the root pyrsistent object where the other arguments are
        located.  See ``PMap.transform`` for the format of this sort of path.

    :param subobj_a: The desired input sub object.

    :param subobj_b: The desired output sub object.

    :returns: An iterable of ``_IDiffChange`` s that will turn ``subobj_a``
        into ``subobj_b``.
    """
    if subobj_a == subobj_b:
        return pvector([])
    elif isinstance(subobj_a, PClass) and isinstance(subobj_b, PClass):
        a_dict = subobj_a._to_dict()
        b_dict = subobj_b._to_dict()
        return _create_diffs_for_mappings(current_path, a_dict, b_dict)
    elif isinstance(subobj_a, PMap) and isinstance(subobj_b, PMap):
        return _create_diffs_for_mappings(
            current_path, subobj_a, subobj_b)
    elif isinstance(subobj_a, PSet) and isinstance(subobj_b, PSet):
        return _create_diffs_for_sets(
            current_path, subobj_a, subobj_b)
    # If the objects are not equal, and there is no intelligent way to recurse
    # inside the objects to make a smaller diff, simply set the current path
    # to the object in b.
    if len(current_path) > 0:
        return pvector([
            _Set(
                path=current_path[:-1],
                key=current_path[-1],
                value=subobj_b
            )
        ])
    # Or if there's no path we're replacing the root object to which subsequent
    # ``_IDiffChange`` operations will be applied.
    else:
        return pvector([
            _Replace(value=subobj_b)
        ])


def create_diff(object_a, object_b):
    """
    Constructs a diff from ``object_a`` to ``object_b``

    :param object_a: The desired input object.

    :param object_b: The desired output object.

    :returns:  A ``Diff`` that will convert ``object_a`` into ``object_b``
        when applied.
    """
    changes = _create_diffs_for(pvector([]), object_a, object_b)
    return Diff(changes=changes)


def compose_diffs(iterable_of_diffs):
    """
    Compose multiple ``Diff`` objects into a single diff.

    Assuming you have 3 objects, A, B, and C and you compute diff AB and BC.
    If you pass [AB, BC] into this function it will return AC, a diff that when
    applied to object A, will return C.

    :param iterable_of_diffs: An iterable of diffs to be composed.

    :returns: A new diff such that applying this diff is equivalent to applying
        each of the input diffs in serial.
    """
    return Diff(
        changes=reduce(
            lambda x, y: x.extend(y.changes),
            iterable_of_diffs,
            pvector().evolver()
        ).persistent()
    )


# Ensure that the representation of a ``Diff`` is entirely serializable:
DIFF_SERIALIZABLE_CLASSES = [
    _Set, _Remove, _Add, Diff, _Replace
]
