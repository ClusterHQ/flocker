# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Utility functions for cluster lifecycle management in test env.
"""

from uuid import UUID

from pyrsistent import PRecord, field, pmap, PMap
from twisted.python.constants import Values, ValueConstant


class TestTypes(Values):
    """
    """
    FUNCTIONAL = ValueConstant("functional")
    ACCEPTANCE = ValueConstant("acceptance")


class Platforms(Values):
    """
    """
    CENTOS7 = ValueConstant("centos-7")
    UBUNTU14 = ValueConstant("ubuntu-14.04")
    UBUNTU15 = ValueConstant("ubuntu-15.04")


class Providers(Values):
    """
    """
    AWS = ValueConstant("aws")
    OPENSTACK = ValueConstant("openstack")


class ClusterIdMarkers(PRecord):
    """
    """
    version = field(mandatory=True, type=long, initial=long(1))
    env_id = field(mandatory=True, type=PMap, factory=pmap, initial=pmap({
        [TestTypes.FUNCTIONAL, Platforms.CENTOS7, Providers.AWS]:
            long(1),
        [TestTypes.FUNCTIONAL, Platforms.CENTOS7, Providers.OPENSTACK]:
            long(2),
        [TestTypes.FUNCTIONAL, Platforms.UBUNTU14, Providers.AWS]:
            long(3),
        [TestTypes.FUNCTIONAL, Platforms.UBUNTU14, Providers.OPENSTACK]:
            long(4),
        [TestTypes.FUNCTIONAL, Platforms.UBUNTU15, Providers.AWS]:
            long(5),
        [TestTypes.FUNCTIONAL, Platforms.UBUNTU15, Providers.OPENSTACK]:
            long(6),
        [TestTypes.ACCEPTANCE, Platforms.CENTOS7, Providers.AWS]:
            long(7),
        [TestTypes.ACCEPTANCE, Platforms.CENTOS7, Providers.OPENSTACK]:
            long(8),
        [TestTypes.ACCEPTANCE, Platforms.UBUNTU14, Providers.AWS]:
            long(9),
        [TestTypes.ACCEPTANCE, Platforms.UBUNTU14, Providers.OPENSTACK]:
            long(10),
        [TestTypes.ACCEPTANCE, Platforms.UBUNTU15, Providers.AWS]:
            long(11),
        [TestTypes.ACCEPTANCE, Platforms.UBUNTU15, Providers.OPENSTACK]:
            long(12)}))
    unsupported_env = field(mandatory=True, type=long, initial=long(99))


def make_cluster_id(test_type, platform, provider):
    """
    Compose cluster ``UUID`` using test type, platform, and provider.
    """
    magic_marker = ClusterIdMarkers.version
    try:
        env_marker = ClusterIdMarkers.env_id[[test_type, platform, provider]]
    except KeyError:
        env_marker = ClusterIdMarkers.unsupported_env

    tagged_cluster_id = UUID(fields=(
        magic_marker, magic_marker, magic_marker, magic_marker, magic_marker,
        env_marker,
    ))
    return tagged_cluster_id
