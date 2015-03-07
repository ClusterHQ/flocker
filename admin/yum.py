# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Effectful interface to RPM tools.
"""

import os

from characteristic import attributes
from effect import sync_performer, TypeDispatcher
from subprocess import check_call
from textwrap import dedent


@attributes([
    "source_repo",
    "target_path",
    "packages",
    "version",
])
class DownloadPackagesFromRepository(object):
    """
    Download a given set of RPMs from a repository.

    Note that this returns a list with the prefixes stripped.

    :ivar bytes source_repo: Location of repoisitory.
    :ivar FilePath target_path: Directory to download packages to.
    :ivar list packages: List of bytes, package names to download.
    :ivar bytes version: Version number of Flocker to download packages for.
    """


@sync_performer
def perform_download_packages_from_repository(dispatcher, intent):
    """
    See :class:`DownloadPackagesFromRepository`.
    """
    yum_repo_config = intent.target_path.child(b'build.repo')
    yum_repo_config.setContent(dedent(b"""
         [flocker]
         name=flocker
         baseurl=%s
         """) % (intent.source_repo,))

    check_call([
        b'yum',
        b'--config', yum_repo_config.path,
        b'--disablerepo=*',
        b'--enablerepo=flocker',
        b'--quiet',
        b'clean',
        b'metadata'])

    check_call([
        b'yumdownloader',
        b'--config', yum_repo_config.path,
        b'--disablerepo=*',
        b'--enablerepo=flocker',
        b'--quiet',
        b'--destdir', intent.target_path.path] + intent.packages)

    # TODO you don't really need to pass version through here
    from admin.release import make_rpm_version
    from admin.packaging import package_filename, PackageTypes

    rpm_version = make_rpm_version(intent.version)
    versioned_packages = [
        package_filename(package_type=PackageTypes.RPM,
                         package=package,
                         architecture='all',
                         rpm_version=rpm_version)
        for package in intent.packages]

    # TODO only return these if there have been changes
    return versioned_packages


@attributes([
    "path",
])
class CreateRepo(object):
    """
    Create repository metadata.

    Note that this returns a list with the prefixes stripped.

    :ivar FilePath path: Location of rpm files to create a repository from.
    """


@sync_performer
def perform_create_repository(dispatcher, intent):
    """
    See :class:`CreateRepo`.

    :return: List of new and modified rpm metadata filenames.
    """
    check_call([
        b'createrepo',
        b'--update',
        b'--quiet',
        intent.path.path])

    # TODO separate this out
    return [os.path.basename(path.path) for path in
            intent.path.child('repodata').walk() if path.isfile()]

yum_dispatcher = TypeDispatcher({
    DownloadPackagesFromRepository: perform_download_packages_from_repository,
    CreateRepo: perform_create_repository,
})


class FakeYum(object):
    """
    Enough of a fake implementation of yum utilities to test
    :func:`admin.release.upload_rpms`.
    """
    # TODO fill in these sync performers
    @sync_performer
    def _perform_download_packages_from_repository(self, dispatcher, intent):
        """
        See :class:`DownloadPackagesFromRepository`.
        """
        from admin.release import make_rpm_version
        from admin.packaging import package_filename, PackageTypes

        rpm_version = make_rpm_version(intent.version)
        versioned_packages = [
            package_filename(package_type=PackageTypes.RPM,
                             package=package,
                             architecture='all',
                             rpm_version=rpm_version)
            for package in intent.packages]

        # TODO only return these if there have been changes
        # TODO put files in target_path
        for package in versioned_packages:
            intent.target_path.child(package).setContent(package)

        return versioned_packages
        # :ivar bytes source_repo: Location of repoisitory.
        # :ivar FilePath target_path: Directory to download packages to.
        # :ivar list packages: List of bytes, package names to download.
        # :ivar bytes version: Version number of Flocker to download packages for.

    @sync_performer
    def _perform_create_repository(self, dispatcher, intent):
        """
        See :class:`CreateRepo`.
        """
        xml_file = intent.path.child('repodata').child('repomd.xml')
        xml_file.parent().makedirs()
        xml_file.touch()

        return [os.path.basename(path.path) for path in
                intent.path.child('repodata').walk() if path.isfile()]

    def get_dispatcher(self):
        """
        Get an :module:`effect` dispatcher for interacting with this
        :class:`FakeYum`.
        """
        return TypeDispatcher({
            DownloadPackagesFromRepository:
                self._perform_download_packages_from_repository,
            CreateRepo: self._perform_create_repository,
        })
