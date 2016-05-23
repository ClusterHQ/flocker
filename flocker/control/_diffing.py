# Copyright ClusterHQ Inc.  See LICENSE file for details.
# -*- test-case-name: flocker.control.test.test_diffing -*-

from pyrsistent import (
    PClass,
    PMap,
    PVector,
    field,
    freeze,
    pvector,
)


class _Remove(PClass):
    path = field(
        type=PVector,
        factory=freeze
    )

    def apply(self, obj):
        obj_path = self.path[:-1]
        removal_path = self.path[-1]
        return obj.transform(obj_path, lambda o: o.remove(removal_path))


class _Set(PClass):
    path = field(
        type=PVector,
        factory=freeze
    )
    val = field()

    def apply(self, obj):
        return obj.transform(self.path, self.val)


class _DeploymentDiff(PClass):
    changes = field(
        type=PVector,
        factory=freeze
    )

    def apply(self, deployment):
        d = deployment
        for c in self.changes:
            d = c.apply(d)
        return d


def _create_diffs_for_mappings(current_path, mapping_a, mapping_b):
    resulting_diffs = pvector([]).evolver()
    a_keys = frozenset(x for x in mapping_a.iterkeys())
    b_keys = frozenset(x for x in mapping_b.iterkeys())
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
            _Set(path=current_path.append(key), val=mapping_b[key])
        )
    for key in a_keys.difference(b_keys):
        resulting_diffs.append(
            _Remove(path=current_path.append(key))
        )
    return resulting_diffs.persistent()


def _create_diffs_for(current_path, subobj_a, subobj_b):
    if subobj_a == subobj_b:
        return pvector([])
    elif type(subobj_a) != type(subobj_b):
        return pvector([_Set(path=current_path, val=subobj_b)])
    elif isinstance(subobj_a, PClass) and isinstance(subobj_b, PClass):
        a_dict = subobj_a._to_dict()
        b_dict = subobj_b._to_dict()
        return _create_diffs_for_mappings(current_path, a_dict, b_dict)
    elif isinstance(subobj_a, PMap) and isinstance(subobj_b, PMap):
        return _create_diffs_for_mappings(
            current_path, subobj_a, subobj_b)
    return pvector([_Set(path=current_path, val=subobj_b)])


def create_deployment_diff(deployment_a, deployment_b):
    changes = _create_diffs_for(pvector([]), deployment_a, deployment_b)
    return _DeploymentDiff(changes=changes)


DIFF_SERIALIZABLE_CLASSES = [
    _Set, _Remove, _DeploymentDiff
]
