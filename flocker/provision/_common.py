# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

from characteristic import attributes, Attribute


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
