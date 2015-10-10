# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

from characteristic import attributes, Attribute
from pyrsistent import PRecord, field
from twisted.python.constants import Values, ValueConstant

from flocker.common.version import make_rpm_version

from ._ca import Certificates


@attributes([
    Attribute('version', default_value=None),
    Attribute('branch', default_value=None),
    Attribute('build_server', default_value="http://build.clusterhq.com/"),
])
class PackageSource(object):
    """
    Source for the installation of a Flocker package.

    :ivar bytes version: The version of Flocker to install. If not specified,
        install the most recent version.
    :ivar bytes branch: The branch from which to install Flocker.
        If not specified, install from the release repository.
    :ivar bytes build_server: The buildserver to install from.
        Only meaningful if a branch is specified.
    """

    def os_version(self):
        """The version of the OS package of Flocker to install."""
        if self.version:
            rpm_version = make_rpm_version(self.version)
            os_version = "%s-%s" % (rpm_version.version, rpm_version.release)
            if os_version.endswith('.dirty'):
                os_version = os_version[:-len('.dirty')]
        else:
            os_version = None
        return os_version


class Variants(Values):
    """
    Provisioning variants for wider acceptance testing coverage.

    :ivar DISTRO_TESTING: Install packages from the distribution's
        proposed-updates repository.
    :ivar DOCKER_HEAD: Install docker from a repository tracking docker HEAD.
    :ivar ZFS_TESTING: Install latest zfs build.
    """
    DISTRO_TESTING = ValueConstant("distro-testing")
    DOCKER_HEAD = ValueConstant("docker-head")
    ZFS_TESTING = ValueConstant("zfs-testing")


class Cluster(PRecord):
    """
    Description of the components of a cluster.

    :ivar list all_nodes: List of all nodes in the cluster.
    :ivar INode control_node: The control node of the cluster.
        tests against.
    :ivar list agent_nodes: The list of INode nodes running flocker
        agent in the cluster.
    :ivar DatasetBackend dataset_backend: The volume backend the nodes are
        configured with.
    :ivar int default_volume_size: The default volume size (in bytes) supported
        by the ``dataset_backend``.
    :ivar FilePath certificates_path: Directory where certificates can be
        found; specifically the directory used by ``Certificates``.
    :ivar Certificates certificates: Certificates to for the cluster.
    """
    all_nodes = field(mandatory=True)
    control_node = field(mandatory=True)
    agent_nodes = field(mandatory=True)
    dataset_backend = field(mandatory=True)
    default_volume_size = field(type=int, mandatory=True)
    certificates = field(type=Certificates, mandatory=True)

    @property
    def certificates_path(self):
        return self.certificates.directory
