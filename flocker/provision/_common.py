# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

from characteristic import attributes, Attribute
from pyrsistent import PRecord, field
from twisted.python.constants import Values, ValueConstant

from ._ca import Certificates


@attributes([
    Attribute('version', default_value=None),
    Attribute('os_version', default_value=None),
    Attribute('branch', default_value=None),
    Attribute('build_server', default_value="http://build.clusterhq.com/"),
])
class PackageSource(object):
    """
    Source for the installation of a flocker package.

    :ivar bytes version: The version of flocker to install. If not specified,
        install the most recent version.
    :ivar bytes os_version: The version of the OS package of flocker to
        install.  If not specified, install the most recent version.
    :ivar bytes branch: The branch from which to install flocker.
        If not specified, install from the release repository.
    :ivar bytes build_server: The builderver to install from.
        Only meaningful if a branch is specified.
    """


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
    :ivar FilePath certificates_path: Directory where certificates can be
        found; specifically the directory used by ``Certificates``.
    :ivar Certificates certificates: Certificates to for the cluster.
    """
    all_nodes = field(mandatory=True)
    control_node = field(mandatory=True)
    agent_nodes = field(mandatory=True)
    dataset_backend = field(mandatory=True)
    certificates = field(type=Certificates, mandatory=True)

    @property
    def certificates_path(self):
        return self.certificates.directory
