# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Utility functions for cluster lifecycle management in test env.
"""

from uuid import uuid4, UUID

from pyrsistent import PRecord, field, pmap, PMap
from twisted.python.constants import Values, ValueConstant


class TestTypes(Values):
    """
    """
    FUNCTIONAL = ValueConstant("functional")
    ACCEPTANCE = ValueConstant("acceptance")


class Providers(Values):
    """
    """
    AWS = ValueConstant("aws")
    OPENSTACK = ValueConstant("openstack")


class ClusterIdMarkers(PRecord):
    """
    """
    version = field(mandatory=True, type=long, initial=long(1))
    test_id = field(mandatory=True, type=PMap, factory=pmap, initial=pmap({
        TestTypes.FUNCTIONAL: long(1),
        TestTypes.ACCEPTANCE: long(2)}))
    provider_id = field(mandatory=True, type=PMap, factory=pmap, initial=pmap({
        Providers.AWS: long(1),
        Providers.OPENSTACK: long(2)}))
    unsupported_env = field(mandatory=True, type=long, initial=long(99))


def make_cluster_id(test_type, provider):
    """
    Compose cluster ``UUID`` using test type, platform, and provider.
    """
    markers = ClusterIdMarkers()
    magic_marker = markers.version

    try:
        test_marker = markers.test_id[test_type]
    except KeyError:
        test_marker = markers.unsupported_env
    try:
        provider_marker = markers.provider_id[
            Providers.lookupByValue(provider)]
    except:
        provider_marker = markers.unsupported_env

    tmp_uuid = uuid4()
    tagged_cluster_id = UUID(fields=(
        tmp_uuid.time_low, tmp_uuid.time_mid, tmp_uuid.time_hi_version,
        # Special magic markers to identify test clusters.
        magic_marker, test_marker, provider_marker,
    ))
    return tagged_cluster_id
