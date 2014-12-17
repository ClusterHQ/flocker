# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

from characteristic import attributes, Attribute


@attributes([
    Attribute('version', default_value=None),
    Attribute('branch', default_value=None),
    Attribute('build_server', default_value="http://build.clusterhq.com/"),
])
class PackageSource(object):
    """
    Source for the installation of a flocker package.

    :ivar version: The version of flocker to install.  The version needs to be
        the OS package version, not the python version.  If not specified,
        install the most recent version.
    :ivar branch: The branch from which to install flocker.
        If not specified, install from the release repository.
    :ivar build_server: The builderver to install from.
        Only meaningful if a branch is specified.
    """
