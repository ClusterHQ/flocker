# Copyright ClusterHQ Inc.  See LICENSE file for details.

from characteristic import attributes, Attribute
from pyrsistent import PClass, field
from zope.interface import (
    Attribute as InterfaceAttribute, Interface)

from twisted.python.constants import Values, ValueConstant
from twisted.python.filepath import FilePath

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


class Cluster(PClass):
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
    :ivar FilePath dataset_backend_config_file: FilePath with the backend
        configuration.
    """
    all_nodes = field(mandatory=True)
    control_node = field(mandatory=True)
    agent_nodes = field(mandatory=True)
    dataset_backend = field(mandatory=True)
    default_volume_size = field(type=int, mandatory=True)
    certificates = field(type=Certificates, mandatory=True)
    dataset_backend_config_file = field(mandatory=True, type=FilePath)

    @property
    def certificates_path(self):
        return self.certificates.directory


class INode(Interface):
    """
    Interface for node for running acceptance tests.
    """
    address = InterfaceAttribute('Public IP address for node')
    private_address = InterfaceAttribute('Private IP address for node')
    distribution = InterfaceAttribute('distribution on node')

    def get_default_username():
        """
        Return the username available by default on a system.

        Some cloud systems (e.g. AWS) provide a specific username, which
        depends on the OS distribution started.  This method returns
        the username based on the node distribution.
        """

    def provision(package_source, variants):
        """
        Provision flocker on this node.

        :param PackageSource package_source: The source from which to install
            flocker.
        :param set variants: The set of variant configurations to use when
            provisioning
        """

    def destroy():
        """
        Destroy the node.
        """

    def reboot():
        """
        Reboot the node.

        :return Effect:
        """


class IProvisioner(Interface):
    """
    A provisioner for creating nodes to run acceptance tests agasint.
    """
    def get_ssh_key():
        """
        Return the public key associated with the provided keyname.

        :return Key: The ssh public key or ``None`` if it can't be determined.
        """

    def create_node(name, distribution,
                    size=None, disk_size=8,
                    metadata={}):
        """
        Create a node.

        :param str name: The name of the node.
        :param str distribution: The name of the distribution to
            install on the node.
        :param str size: The name of the size to use.
        :param int disk_size: The size of disk to allocate.
        :param dict metadata: Metadata to associate with the node.

        :return INode: The created node.
        """
