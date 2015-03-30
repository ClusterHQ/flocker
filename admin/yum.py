# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Effectful interface to packaging tools.
"""

import requests
from requests_file import FileAdapter
from characteristic import attributes
from effect import sync_performer, TypeDispatcher
from subprocess import check_call, check_output
from hashlib import md5
from gzip import GzipFile


@attributes([
    "source_repo",
    "target_path",
    "packages",
    "flocker_version",
    "distro_name",
    "distro_version",
])
class DownloadPackagesFromRepository(object):
    """
    Download a given set of packages from a repository.

    :ivar bytes source_repo: Location of repository.
    :ivar FilePath target_path: Directory to download packages to.
    :ivar list packages: List of bytes, package names to download.
    :param bytes flocker_version: The version of flocker to download packages
        for.
    :param distro_name: The name of the distribution to download packages for.
    :param distro_version: The distro_version of the distribution to download
        packages for.
    """


@sync_performer
def perform_download_packages_from_repository(dispatcher, intent):
    """
    See :class:`DownloadPackagesFromRepository`.
    """
    # XXX Avoid circular imports when importing these somewhere at the top of
    # the file. See https://clusterhq.atlassian.net/browse/FLOC-1223.
    from release import make_rpm_version
    from admin.packaging import (
        PACKAGE_ARCHITECTURE, Distribution,
        package_filename)

    rpm_version = make_rpm_version(intent.flocker_version)
    distribution = Distribution(
        name=intent.distro_name,
        version=intent.distro_version,
    )
    package_type = distribution.package_type()
    s = requests.Session()
    # Tests use a local package repository
    s.mount('file://', FileAdapter())

    downloaded_packages = set()
    for package in intent.packages:
        package_name = package_filename(
            package_type=package_type,
            package=package,
            architecture=PACKAGE_ARCHITECTURE[package],
            rpm_version=rpm_version,
        )
        url = intent.source_repo + '/' + package_name
        local_path = intent.target_path.child(package_name).path
        download = s.get(url)
        try:
         download.raise_for_status()
        except Exception:
            print url
            raise
        content = download.content
        with open(local_path, "wb") as local_file:
            local_file.write(content)
        downloaded_packages.add(package_name)

    return downloaded_packages


@attributes([
    "repository_path",
    "distro_name",
    "distro_version",
])
class CreateRepo(object):
    """
    Create repository metadata, and return filenames of new and changed
    metadata files.

    :ivar FilePath repository_path: Location of package files to create a
        repository from.
    :param distro_name: The name of the distribution to download packages for.
    :param distro_version: The distro_version of the distribution to download
        packages for.

    :return: List of new and modified rpm metadata filenames.
    """


@sync_performer
def perform_create_repository(dispatcher, intent):
    """
    See :class:`CreateRepo`.
    """
    from .packaging import PackageTypes, Distribution

    distribution = Distribution(
        name=intent.distro_name,
        version=intent.distro_version,
    )
    package_type = distribution.package_type()

    if package_type == PackageTypes.RPM:
        # The update option means that this is faster when there is existing
        # metadata but has output starting "Could not find valid repo at:" when
        # there is not existing valid metadata.
        check_call([
            b'createrepo',
            b'--update',
            b'--quiet',
            intent.repository_path.path])
        return _list_new_metadata(repository_path=intent.repository_path)
    elif package_type == PackageTypes.DEB:
        metadata = check_output([
            b'dpkg-scanpackages',
            b'--multiversion',
            intent.repository_path.path])

        with intent.repository_path.child(
                'Packages.gz').open(b"w") as raw_file:
            with GzipFile(b'Packages.gz', fileobj=raw_file) as gzip_file:
                gzip_file.write(metadata)
        return {'Packages.gz'}
    else:
        raise NotImplementedError("Unknwon package type: %s"
                                  % (package_type,))


def _list_new_metadata(repository_path):
    """
    List the filenames of new and changed repository metadata files.

    :param FilePath repository_path: Location of repository to list repository
        metadata from.
    :param set existing_metadata: Filenames of existing metadata files.
    """
    return {"/".join(path.segmentsFrom(repository_path))
            for path in repository_path.child('repodata').walk()}


yum_dispatcher = TypeDispatcher({
    DownloadPackagesFromRepository: perform_download_packages_from_repository,
    CreateRepo: perform_create_repository,
})


class FakeYum(object):
    """
    Enough of a fake implementation of yum utilities to test
    :func:`admin.release.upload_rpms`.
    """
    @sync_performer
    def _perform_create_repository(self, dispatcher, intent):
        """
        See :class:`CreateRepo`.
        """
        from .packaging import PackageTypes, Distribution

        distribution = Distribution(
            name=intent.distro_name,
            version=intent.distro_version,
        )
        package_type = distribution.package_type()

        packages = set([
            file for file in
            intent.repository_path.listdir()
            if file.endswith(package_type.value)])

        if package_type == PackageTypes.RPM:
            metadata_directory = intent.repository_path.child('repodata')
            metadata_directory.createDirectory()
            packages = set([
                file for file in
                intent.repository_path.listdir() if file.endswith('rpm')])

            index_filename = 'repomd.xml'
            for filename in [index_filename, 'filelists.xml.gz',
                             'other.xml.gz', 'primary.xml.gz']:
                content = 'metadata content for: ' + ','.join(packages)

                if filename != index_filename:
                    # The index filename is always the same
                    filename = md5(filename).hexdigest() + '-' + filename
                metadata_directory.child(filename).setContent(content)

            return _list_new_metadata(repository_path=intent.repository_path)
        elif package_type == PackageTypes.DEB:
            index = intent.repository_path.child('Packages.gz')
            index.setContent("Packages.gz for: " + ",".join(packages))
            return {'Packages.gz'}
        else:
            raise NotImplementedError("Unknwon package type: %s"
                                      % (package_type,))

    def get_dispatcher(self):
        """
        Get an :module:`effect` dispatcher for interacting with this
        :class:`FakeYum`.
        """
        return TypeDispatcher({
            # Share implementation with real implementation
            DownloadPackagesFromRepository:
                perform_download_packages_from_repository,

            # Fake implementation
            CreateRepo: self._perform_create_repository,
        })
