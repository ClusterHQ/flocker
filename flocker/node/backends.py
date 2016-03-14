# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Dataset backend descriptions.
"""

from pyrsistent import PClass, field, pset_field

from twisted.python.filepath import FilePath
from twisted.python.constants import Names, NamedConstant


from ..common.plugin import PluginLoader

from ..volume.filesystems import zfs
from ..volume.service import (
    VolumeService, DEFAULT_CONFIG_PATH, FLOCKER_MOUNTPOINT, FLOCKER_POOL)

from .agents.loopback import (
    LoopbackBlockDeviceAPI,
)
from .agents.cinder import cinder_from_configuration
from .agents.ebs import aws_from_configuration
from .agents.gce import gce_from_configuration


def _zfs_storagepool(
        reactor, pool=FLOCKER_POOL, mount_root=None, volume_config_path=None):
    """
    Create a ``VolumeService`` with a ``zfs.StoragePool``.

    :param pool: The name of the ZFS storage pool to use.
    :param bytes mount_root: The path to the directory where ZFS filesystems
        will be mounted.
    :param bytes volume_config_path: The path to the volume service's
        configuration file.

    :return: The ``VolumeService``, started.
    """
    if mount_root is None:
        mount_root = FLOCKER_MOUNTPOINT
    else:
        mount_root = FilePath(mount_root)
    if volume_config_path is None:
        config_path = DEFAULT_CONFIG_PATH
    else:
        config_path = FilePath(volume_config_path)

    pool = zfs.StoragePool(
        reactor=reactor, name=pool, mount_root=mount_root,
    )
    api = VolumeService(
        config_path=config_path,
        pool=pool,
        reactor=reactor,
    )
    api.startService()
    return api


class DeployerType(Names):
    """
    References to the different ``IDeployer`` implementations that are
    available.

    :ivar p2p: The "peer-to-peer" deployer - suitable for use with system like
        ZFS where nodes interact directly with each other for data movement.
    :ivar block: The Infrastructure-as-a-Service deployer - suitable for use
        with system like EBS where volumes can be attached to nodes as block
        devices and then detached (and then re-attached to other nodes).
    """
    p2p = NamedConstant()
    block = NamedConstant()


class BackendDescription(PClass):
    """
    Represent one kind of storage backend we might be able to use.

    :ivar name: The human-meaningful name of this storage backend.
    :ivar needs_reactor: A flag which indicates whether this backend's API
        factory needs to have a reactor passed to it.
    :ivar needs_cluster_id: A flag which indicates whether this backend's API
        factory needs to have the cluster's unique identifier passed to it.
    :ivar api_factory: An object which can be called with some simple
        configuration data and which returns the API object implementing this
        storage backend.
    :ivar required_config: A set of the dataset configuration keys
        required to initialize this backend.
    :type required_config: ``PSet`` of ``unicode``
    :ivar deployer_type: A constant from ``DeployerType`` indicating which kind
        of ``IDeployer`` the API object returned by ``api_factory`` is usable
        with.
    """
    name = field(type=unicode, mandatory=True)
    needs_reactor = field(type=bool, mandatory=True)
    # XXX Eventually everyone will take cluster_id so we will throw this flag
    # out.
    needs_cluster_id = field(type=bool, mandatory=True)
    # Config "dataset" keys required to initialize this backend.
    required_config = pset_field(unicode)
    api_factory = field(mandatory=True)
    deployer_type = field(
        mandatory=True,
        invariant=lambda value: (
            value in DeployerType.iterconstants(), "Unknown deployer_type"
        ),
    )

# These structures should be created dynamically to handle plug-ins
_DEFAULT_BACKENDS = [
    # P2PManifestationDeployer doesn't currently know anything about
    # cluster_uuid.  It probably should so that it can make sure it
    # only talks to other nodes in the same cluster (maybe the
    # authentication layer would mostly handle this but maybe not if
    # you're slightly careless with credentials - also ZFS backend
    # doesn't use TLS yet).
    BackendDescription(
        name=u"zfs", needs_reactor=True, needs_cluster_id=False,
        api_factory=_zfs_storagepool, deployer_type=DeployerType.p2p,
    ),
    BackendDescription(
        name=u"loopback", needs_reactor=False, needs_cluster_id=False,
        # XXX compute_instance_id is the wrong type
        api_factory=LoopbackBlockDeviceAPI.from_path,
        deployer_type=DeployerType.block,
    ),
    BackendDescription(
        name=u"openstack", needs_reactor=False, needs_cluster_id=True,
        api_factory=cinder_from_configuration,
        deployer_type=DeployerType.block,
        required_config={u"region"},
    ),
    BackendDescription(
        name=u"aws", needs_reactor=False, needs_cluster_id=True,
        api_factory=aws_from_configuration,
        deployer_type=DeployerType.block,
        required_config={
            u"region", u"zone", u"access_key_id", u"secret_access_key",
        },
    ),
    BackendDescription(
        name=u"gce", needs_reactor=False, needs_cluster_id=True,
        api_factory=gce_from_configuration,
        deployer_type=DeployerType.block,
        required_config=set([]),
    ),
]

backend_loader = PluginLoader(
    builtin_plugins=_DEFAULT_BACKENDS,
    module_attribute="FLOCKER_BACKEND",
    plugin_type=BackendDescription,
)

# Backend constants for acceptance test usage.
AWS = backend_loader.get('aws')
OPENSTACK = backend_loader.get('openstack')
LOOPBACK = backend_loader.get('loopback')
ZFS = backend_loader.get('zfs')
GCE = backend_loader.get('gce')
