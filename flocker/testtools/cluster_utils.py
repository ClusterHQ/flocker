# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Utility functions for cluster lifecycle management in test env.
"""

from uuid import uuid4, UUID

from pyrsistent import PRecord, field, pmap, PMap
from twisted.python.constants import Values, ValueConstant


class TestTypes(Values):
    """
    Supported test types.
    """
    FUNCTIONAL = ValueConstant("functional")
    ACCEPTANCE = ValueConstant("acceptance")


class Providers(Values):
    """
    Supported storage providers.
    """
    AWS = ValueConstant("aws")
    OPENSTACK = ValueConstant("openstack")


class ClusterIdMarkers(PRecord):
    """
    ``PRecord`` to hold data used to seed cluster id for test clusters.

    Please increment ``version`` in case of changes to supported test types
    and storage providers.
    """
    version = field(mandatory=True, type=long, initial=long(1))
    test_id = field(mandatory=True, type=PMap, factory=pmap, initial=pmap({
        TestTypes.FUNCTIONAL: long(1),
        TestTypes.ACCEPTANCE: long(2)}))
    provider_id = field(mandatory=True, type=PMap, factory=pmap, initial=pmap({
        Providers.AWS: long(1),
        Providers.OPENSTACK: long(2)}))
    unsupported_env = field(mandatory=True, type=long, initial=long(99))


def make_cluster_id(test_type, provider='unknown'):
    """
    Compose cluster ``UUID`` using test type and storage provider.

    :param TestTypes test_type: Intended type of test that will use cluster id.
    :param str provider: Storage provider on which cluster will be deployed.
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
        # Use ``UUID``'s clock_seq_hi_variant field to store ClusterIdMarkers
        # version, clock_seq_low field to store test type,
        # and node field to store provider name.
        magic_marker, test_marker, provider_marker,
    ))
    return tagged_cluster_id
