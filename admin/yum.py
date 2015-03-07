# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Effectful interface to RPM tools.
"""

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
    Download the S3 files from a key a bucket.

    Note that this returns a list with the prefixes stripped.

    :ivar bytes bucket: Name of bucket to list keys from.
    :ivar bytes prefix: Prefix of keys to be listed.
    # TODO document this and performer docstring
    # TODO pyrsistent
    """


@sync_performer
def perform_download_packages_from_repository(dispatcher, intent):
    yum_repo_config = intent.target_path.child(b'build.repo')
    yum_repo_config.setContent(dedent(b"""
         [flocker]
         name=flocker
         baseurl=%s
         """) % (intent.source_repo,))

    check_call([
        b'yum',
        b'-c', yum_repo_config.path,
        b'--disablerepo=*',
        b'--enablerepo=flocker',
        b'clean',
        b'metadata'])

    check_call([
        b'yumdownloader',
        b'-c', yum_repo_config.path,
        b'--disablerepo=*',
        b'--enablerepo=flocker',
        b'--destdir', intent.target_path.path] + intent.packages)

    # TODO you don't really need to pass version through here
    # TODO This is RPM specific. Support other packages?
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
    Download the S3 files from a key a bucket.

    Note that this returns a list with the prefixes stripped.

    :ivar bytes bucket: Name of bucket to list keys from.
    :ivar bytes prefix: Prefix of keys to be listed.
    # TODO document this and performer docstring
    # TODO pyrsistent
    """


@sync_performer
def perform_create_repository(dispatcher, intent):
    check_call([b'createrepo', b'--update', intent.path.path])
    # TODO return new repository files
    return []

yum_dispatcher = TypeDispatcher({
    DownloadPackagesFromRepository: perform_download_packages_from_repository,
    CreateRepo: perform_create_repository,
})


class FakeYum(object):
    """
    # TODO Document

    Enough of a fake implementation of AWS to test
    :func:`admin.release.publish_docs`.

    :ivar routing_rules: Dictionary of routing rules for S3 buckets. They are
        represented as dictonaries mapping key prefixes to replacements. Other
        types of rules and attributes are supported or represented.
    :ivar s3_buckets: Dictionary of fake S3 buckets. Each bucket is represented
        as a dictonary mapping keys to contents. Other attributes are ignored.
    :ivar cloudfront_invalidations: List of
        :class:`CreateCloudFrontInvalidation` that have been requested.
    """
    def __init__(self):
        self.cloudfront_invalidations = []

    @sync_performer
    def _perform_update_s3_routing_rule(self, dispatcher, intent):
        """
        See :class:`UpdateS3RoutingRule`.
        """
        old_target = self.routing_rules[intent.bucket][intent.prefix]
        self.routing_rules[intent.bucket][intent.prefix] = intent.target_prefix
        return old_target

    def get_dispatcher(self):
        """
        Get an :module:`effect` dispatcher for interacting with this
        :class:`FakeAWS`.
        """
        return TypeDispatcher({
            DownloadPackagesFromRepository:
                perform_download_packages_from_repository,
            CreateRepo: perform_create_repository,
        })
