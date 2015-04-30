# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

from characteristic import attributes, Attribute
from twisted.python.constants import Values, ValueConstant


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
