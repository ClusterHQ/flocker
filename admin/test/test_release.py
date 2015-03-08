# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``admin.release``.
"""

import os
from unittest import TestCase
import tempfile
from effect import sync_perform, ComposedDispatcher, base_dispatcher

from twisted.python.filepath import FilePath

from ..release import (
    rpm_version, make_rpm_version, upload_rpms, update_repo,
    publish_docs, Environments,
    DocumentationRelease, NotTagged, NotARelease,
)
from ..aws import FakeAWS, CreateCloudFrontInvalidation
from ..yum import FakeYum, yum_dispatcher


class MakeRpmVersionTests(TestCase):
    """
    Tests for ``make_rpm_version``.
    """
    def test_good(self):
        """
        ``make_rpm_version`` gives the expected ``rpm_version`` instances when
        supplied with valid ``flocker_version_number``s.
        """
        expected = {
            '0.1.0': rpm_version('0.1.0', '1'),
            '0.1.0-99-g3d644b1': rpm_version('0.1.0', '1.99.g3d644b1'),
            '0.1.1pre1': rpm_version('0.1.1', '0.pre.1'),
            '0.1.1': rpm_version('0.1.1', '1'),
            '0.2.0dev1': rpm_version('0.2.0', '0.dev.1'),
            '0.2.0dev2-99-g3d644b1':
                rpm_version('0.2.0', '0.dev.2.99.g3d644b1'),
            '0.2.0dev3-100-g3d644b2-dirty': rpm_version(
                '0.2.0', '0.dev.3.100.g3d644b2.dirty'),
        }
        unexpected_results = []
        for supplied_version, expected_rpm_version in expected.items():
            actual_rpm_version = make_rpm_version(supplied_version)
            if actual_rpm_version != expected_rpm_version:
                unexpected_results.append((
                    supplied_version,
                    actual_rpm_version,
                    expected_rpm_version,
                ))

        if unexpected_results:
            self.fail(unexpected_results)

    def test_non_integer_suffix(self):
        """
        ``make_rpm_version`` raises ``Exception`` when supplied with a version
        with a non-integer pre or dev suffix number.
        """
        with self.assertRaises(Exception) as exception:
            make_rpm_version('0.1.2preX')

        self.assertEqual(
            u'Non-integer value "X" for "pre". Supplied version 0.1.2preX',
            unicode(exception.exception),
        )


class PublishDocsTests(TestCase):
    """
    Tests for :func:``publish_docs``.
    """

    def publish_docs(self, aws,
                     flocker_version, doc_version, environment):
        """
        Call :func:``publish_docs``, interacting with a fake AWS.

        :param FakeAWS aws: Fake AWS to interact with.
        :param flocker_version: See :py:func:`publish_docs`.
        :param doc_version: See :py:func:`publish_docs`.
        :param environment: See :py:func:`environment`.
        """
        sync_perform(
            ComposedDispatcher([aws.get_dispatcher(), base_dispatcher]),
            publish_docs(flocker_version, doc_version,
                         environment=environment))

    def test_copies_documentation(self):
        """
        Calling :func:`publish_docs` copies documentation from
        ``s3://clusterhq-dev-docs/<flocker_version>/`` to
        ``s3://clusterhq-staging-docs/en/<doc_version>/``.
        """
        aws = FakeAWS(
            routing_rules={
                'clusterhq-staging-docs': {
                    'en/latest/': 'en/0.3.0/',
                },
            },
            s3_buckets={
                'clusterhq-staging-docs': {
                    'index.html': '',
                    'en/index.html': '',
                    'en/latest/index.html': '',
                },
                'clusterhq-dev-docs': {
                    '0.3.0-444-gf05215b/index.html': 'index-content',
                    '0.3.0-444-gf05215b/sub/index.html': 'sub-index-content',
                    '0.3.0-444-gf05215b/other.html': 'other-content',
                    '0.3.0-392-gd50b558/index.html': 'bad-index',
                    '0.3.0-392-gd50b558/sub/index.html': 'bad-sub-index',
                    '0.3.0-392-gd50b558/other.html': 'bad-other',
                },
            })
        self.publish_docs(aws, '0.3.0-444-gf05215b', '0.3.1',
                          environment=Environments.STAGING)
        self.assertEqual(
            aws.s3_buckets['clusterhq-staging-docs'], {
                'index.html': '',
                'en/index.html': '',
                'en/latest/index.html': '',
                'en/0.3.1/index.html': 'index-content',
                'en/0.3.1/sub/index.html': 'sub-index-content',
                'en/0.3.1/other.html': 'other-content',
            })

    def test_copies_documentation_production(self):
        """
        Calling :func:`publish_docs` in production copies documentation from
        ``s3://clusterhq-dev-docs/<flocker_version>/`` to
        ``s3://clusterhq-docs/en/<doc_version>/``.
        """
        aws = FakeAWS(
            routing_rules={
                'clusterhq-docs': {
                    'en/latest/': 'en/0.3.0/',
                },
            },
            s3_buckets={
                'clusterhq-docs': {
                    'index.html': '',
                    'en/index.html': '',
                    'en/latest/index.html': '',
                },
                'clusterhq-dev-docs': {
                    '0.3.1/index.html': 'index-content',
                    '0.3.1/sub/index.html': 'sub-index-content',
                    '0.3.1/other.html': 'other-content',
                    '0.3.0-392-gd50b558/index.html': 'bad-index',
                    '0.3.0-392-gd50b558/sub/index.html': 'bad-sub-index',
                    '0.3.0-392-gd50b558/other.html': 'bad-other',
                },
            })
        self.publish_docs(aws, '0.3.1', '0.3.1',
                          environment=Environments.PRODUCTION)
        self.assertEqual(
            aws.s3_buckets['clusterhq-docs'], {
                'index.html': '',
                'en/index.html': '',
                'en/latest/index.html': '',
                'en/0.3.1/index.html': 'index-content',
                'en/0.3.1/sub/index.html': 'sub-index-content',
                'en/0.3.1/other.html': 'other-content',
            })

    def test_deletes_removed_documentation(self):
        """
        Calling :func:`publish_docs` replaces documentation from
        ``s3://clusterhq-staging-docs/en/<doc_version>/``.
        with documentation from ``s3://clusterhq-dev-docs/<flocker_version>/``.
        In particular, files with changed content are updated, and removed
        files are deleted.
        """
        aws = FakeAWS(
            routing_rules={
                'clusterhq-staging-docs': {
                    'en/latest/': 'en/0.3.0/',
                },
            },
            s3_buckets={
                'clusterhq-staging-docs': {
                    'index.html': '',
                    'en/index.html': '',
                    'en/latest/index.html': '',
                    'en/0.3.1/index.html': 'old-index-content',
                    'en/0.3.1/sub/index.html': 'old-sub-index-content',
                    'en/0.3.1/other.html': 'other-content',
                },
                'clusterhq-dev-docs': {
                    '0.3.0-444-gf05215b/index.html': 'index-content',
                    '0.3.0-444-gf05215b/sub/index.html': 'sub-index-content',
                },
            })
        self.publish_docs(aws, '0.3.0-444-gf05215b', '0.3.1',
                          environment=Environments.STAGING)
        self.assertEqual(
            aws.s3_buckets['clusterhq-staging-docs'], {
                'index.html': '',
                'en/index.html': '',
                'en/latest/index.html': '',
                'en/0.3.1/index.html': 'index-content',
                'en/0.3.1/sub/index.html': 'sub-index-content',
            })

    def test_updates_redirects(self):
        """
        Calling :func:`publish_docs` with a release version updates the
        redirect for ``en/latest/*`` to point at ``en/<doc_version>/*``. Any
        other redirects are left untouched.
        """
        aws = FakeAWS(
            routing_rules={
                'clusterhq-staging-docs': {
                    'en/latest/': 'en/0.3.0/',
                    'en/devel/': 'en/0.3.1.dev4/',
                },
            },
            s3_buckets={
                'clusterhq-staging-docs': {},
                'clusterhq-dev-docs': {},
            })
        self.publish_docs(aws, '0.3.0-444-gf05215b', '0.3.1',
                          environment=Environments.STAGING)
        self.assertEqual(
            aws.routing_rules, {
                'clusterhq-staging-docs': {
                    'en/latest/': 'en/0.3.1/',
                    'en/devel/': 'en/0.3.1.dev4/',
                },
            })

    def test_updates_redirects_devel(self):
        """
        Calling :func:`publish_docs` for a development version updates the
        redirect for ``en/devel/*`` to point at ``en/<doc_version>/*``. Any
        other redirects are left untouched.
        """
        aws = FakeAWS(
            routing_rules={
                'clusterhq-staging-docs': {
                    'en/latest/': 'en/0.3.0/',
                    'en/devel/': 'en/0.3.1dev4/',
                },
            },
            s3_buckets={
                'clusterhq-staging-docs': {},
                'clusterhq-dev-docs': {},
            })
        self.publish_docs(aws, '0.3.0-444-gf01215b', '0.3.1dev5',
                          environment=Environments.STAGING)
        self.assertEqual(
            aws.routing_rules, {
                'clusterhq-staging-docs': {
                    'en/latest/': 'en/0.3.0/',
                    'en/devel/': 'en/0.3.1dev5/',
                },
            })

    def test_updates_redirects_production(self):
        """
        Calling :func:`publish_docs` with a release or documentation version
        and in production updates the redirect for the
        ``clusterhq-docs`` S3 bucket.
        """
        aws = FakeAWS(
            routing_rules={
                'clusterhq-docs': {
                    'en/latest/': 'en/0.3.0/',
                    'en/devel/': 'en/0.3.1.dev4/',
                },
            },
            s3_buckets={
                'clusterhq-docs': {},
                'clusterhq-dev-docs': {},
            })
        self.publish_docs(aws, '0.3.1', '0.3.1',
                          environment=Environments.PRODUCTION)
        self.assertEqual(
            aws.routing_rules, {
                'clusterhq-docs': {
                    'en/latest/': 'en/0.3.1/',
                    'en/devel/': 'en/0.3.1.dev4/',
                },
            })

    def test_creates_cloudfront_invalidation_new_files(self):
        """
        Calling :func:`publish_docs` with a release or documentation version
        creates an invalidation for
        - en/latest/
        - en/<doc_version>/
        each for every path in the new documentation for <doc_version>.
        """
        aws = FakeAWS(
            routing_rules={
                'clusterhq-staging-docs': {
                    'en/latest/': 'en/0.3.0/',
                },
            },
            s3_buckets={
                'clusterhq-staging-docs': {
                    'index.html': '',
                    'en/index.html': '',
                    'en/latest/index.html': '',
                    'en/0.3.1/index.html': '',
                    'en/0.3.1/sub/index.html': '',
                },
                'clusterhq-dev-docs': {
                    '0.3.0-444-gf05215b/index.html': '',
                    '0.3.0-444-gf05215b/sub/index.html': '',
                    '0.3.0-444-gf05215b/sub/other.html': '',
                },
            })
        self.publish_docs(aws, '0.3.0-444-gf05215b', '0.3.1',
                          environment=Environments.STAGING)
        self.assertEqual(
            aws.cloudfront_invalidations, [
                CreateCloudFrontInvalidation(
                    cname='docs.staging.clusterhq.com',
                    paths={
                        'en/latest/',
                        'en/latest/index.html',
                        'en/latest/sub/',
                        'en/latest/sub/index.html',
                        'en/latest/sub/other.html',
                        'en/0.3.1/',
                        'en/0.3.1/index.html',
                        'en/0.3.1/sub/',
                        'en/0.3.1/sub/index.html',
                        'en/0.3.1/sub/other.html',
                    }),
            ])

    def test_creates_cloudfront_invalidation_trailing_index(self):
        """
        Calling :func:`publish_docs` with a release or documentation version
        doesn't creates an invalidation for files that end in ``index.html``.
        """
        aws = FakeAWS(
            routing_rules={
                'clusterhq-staging-docs': {
                    'en/latest/': 'en/0.3.0/',
                },
            },
            s3_buckets={
                'clusterhq-staging-docs': {
                    'index.html': '',
                    'en/index.html': '',
                    'en/latest/index.html': '',
                },
                'clusterhq-dev-docs': {
                    '0.3.0-444-gf05215b/sub_index.html': '',
                },
            })
        self.publish_docs(aws, '0.3.0-444-gf05215b', '0.3.1',
                          environment=Environments.STAGING)
        self.assertEqual(
            aws.cloudfront_invalidations, [
                CreateCloudFrontInvalidation(
                    cname='docs.staging.clusterhq.com',
                    paths={
                        'en/latest/',
                        'en/latest/sub_index.html',
                        'en/0.3.1/',
                        'en/0.3.1/sub_index.html',
                    }),
            ])

    def test_creates_cloudfront_invalidation_removed_files(self):
        """
        Calling :func:`publish_docs` with a release or documentation version
        creates an invalidation for
        - en/latest/
        - en/<doc_version>/
        each for every path in the old documentation for <doc_version>.
        """
        aws = FakeAWS(
            routing_rules={
                'clusterhq-staging-docs': {
                    'en/latest/': 'en/0.3.0/',
                },
            },
            s3_buckets={
                'clusterhq-staging-docs': {
                    'index.html': '',
                    'en/index.html': '',
                    'en/latest/index.html': '',
                    'en/0.3.1/index.html': '',
                    'en/0.3.1/sub/index.html': '',
                },
                'clusterhq-dev-docs': {},
            })
        self.publish_docs(aws, '0.3.0-444-gf05215b', '0.3.1',
                          environment=Environments.STAGING)
        self.assertEqual(
            aws.cloudfront_invalidations, [
                CreateCloudFrontInvalidation(
                    cname='docs.staging.clusterhq.com',
                    paths={
                        'en/latest/',
                        'en/latest/index.html',
                        'en/latest/sub/',
                        'en/latest/sub/index.html',
                        'en/0.3.1/',
                        'en/0.3.1/index.html',
                        'en/0.3.1/sub/',
                        'en/0.3.1/sub/index.html',
                    }),
            ])

    def test_creates_cloudfront_invalidation_previous_version(self):
        """
        Calling :func:`publish_docs` with a release or documentation version
        creates an invalidation for
        - en/latest/
        - en/<doc_version>/
        each for every path in the documentation for version that was
        previously `en/latest/`.
        """
        aws = FakeAWS(
            routing_rules={
                'clusterhq-staging-docs': {
                    'en/latest/': 'en/0.3.0/',
                },
            },
            s3_buckets={
                'clusterhq-staging-docs': {
                    'index.html': '',
                    'en/index.html': '',
                    'en/latest/index.html': '',
                    'en/0.3.0/index.html': '',
                    'en/0.3.0/sub/index.html': '',
                },
                'clusterhq-dev-docs': {},
            })
        self.publish_docs(aws, '0.3.0-444-gf05215b', '0.3.1',
                          environment=Environments.STAGING)
        self.assertEqual(
            aws.cloudfront_invalidations, [
                CreateCloudFrontInvalidation(
                    cname='docs.staging.clusterhq.com',
                    paths={
                        'en/latest/',
                        'en/latest/index.html',
                        'en/latest/sub/',
                        'en/latest/sub/index.html',
                        'en/0.3.1/',
                        'en/0.3.1/index.html',
                        'en/0.3.1/sub/',
                        'en/0.3.1/sub/index.html',
                    }),
            ])

    def test_creates_cloudfront_invalidation_devel_new_files(self):
        """
        Calling :func:`publish_docs` with a development version creates an
        invalidation for
        - en/devel/
        - en/<doc_version>/
        each for every path in the new documentation for <doc_version>.
        """
        aws = FakeAWS(
            routing_rules={
                'clusterhq-staging-docs': {
                    'en/devel/': 'en/0.3.0/',
                },
            },
            s3_buckets={
                'clusterhq-staging-docs': {
                    'index.html': '',
                    'en/index.html': '',
                    'en/devel/index.html': '',
                    'en/0.3.1dev1/index.html': '',
                    'en/0.3.1dev1/sub/index.html': '',
                },
                'clusterhq-dev-docs': {
                    '0.3.0-444-gf05215b/index.html': '',
                    '0.3.0-444-gf05215b/sub/index.html': '',
                    '0.3.0-444-gf05215b/sub/other.html': '',
                },
            })
        self.publish_docs(aws, '0.3.0-444-gf05215b', '0.3.1dev1',
                          environment=Environments.STAGING)
        self.assertEqual(
            aws.cloudfront_invalidations, [
                CreateCloudFrontInvalidation(
                    cname='docs.staging.clusterhq.com',
                    paths={
                        'en/devel/',
                        'en/devel/index.html',
                        'en/devel/sub/',
                        'en/devel/sub/index.html',
                        'en/devel/sub/other.html',
                        'en/0.3.1dev1/',
                        'en/0.3.1dev1/index.html',
                        'en/0.3.1dev1/sub/',
                        'en/0.3.1dev1/sub/index.html',
                        'en/0.3.1dev1/sub/other.html',
                    }),
            ])

    def test_creates_cloudfront_invalidation_devel_removed_files(self):
        """
        Calling :func:`publish_docs` with a development version creates an
        invalidation for
        - en/devel/
        - en/<doc_version>/
        each for every path in the old documentation for <doc_version>.
        """
        aws = FakeAWS(
            routing_rules={
                'clusterhq-staging-docs': {
                    'en/devel/': 'en/0.3.0/',
                },
            },
            s3_buckets={
                'clusterhq-staging-docs': {
                    'index.html': '',
                    'en/index.html': '',
                    'en/devel/index.html': '',
                    'en/0.3.1dev1/index.html': '',
                    'en/0.3.1dev1/sub/index.html': '',
                },
                'clusterhq-dev-docs': {},
            })
        self.publish_docs(aws, '0.3.0-444-gf05215b', '0.3.1dev1',
                          environment=Environments.STAGING)
        self.assertEqual(
            aws.cloudfront_invalidations, [
                CreateCloudFrontInvalidation(
                    cname='docs.staging.clusterhq.com',
                    paths={
                        'en/devel/',
                        'en/devel/index.html',
                        'en/devel/sub/',
                        'en/devel/sub/index.html',
                        'en/0.3.1dev1/',
                        'en/0.3.1dev1/index.html',
                        'en/0.3.1dev1/sub/',
                        'en/0.3.1dev1/sub/index.html',
                    }),
            ])

    def test_creates_cloudfront_invalidation_devel_previous_version(self):
        """
        Calling :func:`publish_docs` with a development version creates an
        invalidation for
        - en/devel/
        - en/<doc_version>/
        each for every path in the documentation for version that was
        previously `en/devel/`.
        """
        aws = FakeAWS(
            routing_rules={
                'clusterhq-staging-docs': {
                    'en/devel/': 'en/0.3.0/',
                },
            },
            s3_buckets={
                'clusterhq-staging-docs': {
                    'index.html': '',
                    'en/index.html': '',
                    'en/devel/index.html': '',
                    'en/0.3.0/index.html': '',
                    'en/0.3.0/sub/index.html': '',
                },
                'clusterhq-dev-docs': {},
            })
        self.publish_docs(aws, '0.3.0-444-gf05215b', '0.3.1dev1',
                          environment=Environments.STAGING)
        self.assertEqual(
            aws.cloudfront_invalidations, [
                CreateCloudFrontInvalidation(
                    cname='docs.staging.clusterhq.com',
                    paths={
                        'en/devel/',
                        'en/devel/index.html',
                        'en/devel/sub/',
                        'en/devel/sub/index.html',
                        'en/0.3.1dev1/',
                        'en/0.3.1dev1/index.html',
                        'en/0.3.1dev1/sub/',
                        'en/0.3.1dev1/sub/index.html',
                    }),
            ])

    def test_creates_cloudfront_invalidation_production(self):
        """
        Calling :func:`publish_docs` in production creates an invalidation for
        ``docs.clusterhq.com``.
        """
        aws = FakeAWS(
            routing_rules={
                'clusterhq-docs': {
                    'en/latest/': 'en/0.3.0/',
                },
            },
            s3_buckets={
                'clusterhq-docs': {
                    'index.html': '',
                    'en/index.html': '',
                    'en/latest/index.html': '',
                    'en/0.3.1/index.html': '',
                    'en/0.3.1/sub/index.html': '',
                },
                'clusterhq-dev-docs': {},
            })
        self.publish_docs(aws, '0.3.1', '0.3.1',
                          environment=Environments.PRODUCTION)
        self.assertEqual(
            aws.cloudfront_invalidations, [
                CreateCloudFrontInvalidation(
                    cname='docs.clusterhq.com',
                    paths={
                        'en/latest/',
                        'en/latest/index.html',
                        'en/latest/sub/',
                        'en/latest/sub/index.html',
                        'en/0.3.1/',
                        'en/0.3.1/index.html',
                        'en/0.3.1/sub/',
                        'en/0.3.1/sub/index.html',
                    }),
            ])

    def test_production_gets_tagged_version(self):
        """
        Trying to publish to production, when the version being pushed isn't
        tagged raises an exception.
        """
        aws = FakeAWS(routing_rules={}, s3_buckets={})
        self.assertRaises(
            NotTagged,
            self.publish_docs,
            aws, '0.3.0-444-gf05215b', '0.3.1dev1',
            environment=Environments.PRODUCTION)

    def test_production_can_publish_doc_version(self):
        """
        Publishing a documentation version to the version of the latest full
        release in production succeeds.
        """
        aws = FakeAWS(
            routing_rules={
                'clusterhq-docs': {
                    'en/latest/': 'en/0.3.0/',
                },
            },
            s3_buckets={
                'clusterhq-docs': {},
                'clusterhq-dev-docs': {},
            })
        # Does not raise:
        self.publish_docs(
            aws, '0.3.1+doc1', '0.3.1', environment=Environments.PRODUCTION)

    def test_publish_non_release_fails(self):
        """
        Trying to publish to version that isn't a release fails.
        """
        aws = FakeAWS(routing_rules={}, s3_buckets={})
        self.assertRaises(
            NotARelease,
            self.publish_docs,
            aws, '0.3.0-444-gf05215b', '0.3.0-444-gf05215b',
            environment=Environments.STAGING)


class UploadRPMsTests(TestCase):
    """
    Tests for :func:``upload_rpms``.
    """
    def upload_rpms(self, aws, yum,
                    scratch_directory, target_bucket, version, build_server):
        """
        Call :func:``upload_rpms``, interacting with a fake AWS and yum
        utilities.

        :param FakeAWS aws: Fake AWS to interact with.
        :param FakeYum yum: Fake yum utilities to interact with.
        :param rpm_directory: See :py:func:`update_repo`.
        :param target_bucket: See :py:func:`update_repo`.
        :param target_key: See :py:func:`update_repo`.
        :param source_repo: See :py:func:`update_repo`.
        :param packages: See :py:func:`update_repo`.
        :param version: See :py:func:`update_repo`.
        """
        dispatchers = [aws.get_dispatcher(), yum.get_dispatcher(),
                       base_dispatcher]
        sync_perform(
            ComposedDispatcher(dispatchers),
            upload_rpms(
                scratch_directory=scratch_directory,
                target_bucket=target_bucket,
                version=version,
                build_server=build_server,
            ),
        )

    def update_repo(self, aws, yum,
                    rpm_directory, target_bucket, target_key, source_repo,
                    packages):
        """
        Call :func:``update_repo``, interacting with a fake AWS and yum
        utilities.

        :param FakeAWS aws: Fake AWS to interact with.
        :param FakeYum yum: Fake yum utilities to interact with.
        :param rpm_directory: See :py:func:`update_repo`.
        :param target_bucket: See :py:func:`update_repo`.
        :param target_key: See :py:func:`update_repo`.
        :param source_repo: See :py:func:`update_repo`.
        :param packages: See :py:func:`update_repo`.
        :param version: See :py:func:`update_repo`.
        """
        dispatchers = [aws.get_dispatcher(), yum.get_dispatcher(),
                       base_dispatcher]
        sync_perform(
            ComposedDispatcher(dispatchers),
            update_repo(rpm_directory, target_bucket, target_key, source_repo,
                        packages))

    def create_fake_repository(self, files):
        """
        Create files in a directory to mimic a repository of packages.

        :param dict source_repo: Dictionary mapping names of files to create to
            contents.
        :return: FilePath of directory containing fake package files.
        """
        source_repo = FilePath(tempfile.mkdtemp())
        for key in files:
            new_file = source_repo.preauthChild(key)
            if not new_file.parent().exists():
                new_file.parent().makedirs()
            new_file.setContent(files[key])
        return 'file://' + source_repo.path

    def setUp(self):
        self.scratch_directory = FilePath(tempfile.mkdtemp())
        self.addCleanup(self.scratch_directory.remove)
        self.rpm_directory = self.scratch_directory.child(
            b'distro-version-arch')
        self.target_key = 'test/target/key'
        self.target_bucket = 'test-target-bucket'
        self.build_server = 'http://test-build-server.com'
        self.packages = ['clusterhq-flocker-cli', 'clusterhq-flocker-node']
        self.alternative_bucket = 'bucket-with-existing-package'
        alt_scratch_directory = FilePath(tempfile.mkdtemp())
        self.addCleanup(alt_scratch_directory.remove)
        self.alternative_package_directory = alt_scratch_directory.child(
            b'distro-version-arch')
        self.operating_systems = [
            {'distro': 'fedora', 'version': '20', 'arch': 'x86_64'},
            {'distro': 'centos', 'version': '7', 'arch': 'x86_64'},
        ]

    def test_upload_non_release_fails(self):
        """
        Calling :func:`upload_rpms` with a version that isn't a release fails.
        """
        aws = FakeAWS(
            routing_rules={},
            s3_buckets={},
        )
        yum = FakeYum()

        self.assertRaises(
            NotARelease,
            self.upload_rpms, aws, yum,
            self.rpm_directory, self.target_bucket, '0.3.0-444-gf05215b',
            self.build_server)

    def test_upload_doc_release_fails(self):
        """
        Calling :func:`upload_rpms` with a documentation release version fails.
        """
        aws = FakeAWS(
            routing_rules={},
            s3_buckets={},
        )
        yum = FakeYum()

        self.assertRaises(
            DocumentationRelease,
            self.upload_rpms, aws, yum,
            self.rpm_directory, self.target_bucket, '0.3.0+doc1',
            self.build_server)

    def test_packages_uploaded(self):
        """
        Calling :func:`update_repo` uploads packages from a source repository
        to S3.
        """
        aws = FakeAWS(
            routing_rules={},
            s3_buckets={
                self.target_bucket: {},
            },
        )

        repo_contents = {
            'clusterhq-flocker-cli-0.3.3-0.dev.7.noarch.rpm': 'cli-package',
            'clusterhq-flocker-node-0.3.3-0.dev.7.noarch.rpm': 'node-package',
        }

        self.update_repo(
            aws=aws,
            yum=FakeYum(),
            rpm_directory=self.rpm_directory,
            target_bucket=self.target_bucket,
            target_key=self.target_key,
            source_repo=self.create_fake_repository(files=repo_contents),
            packages=self.packages,
        )

        self.assertDictContainsSubset(
            {os.path.join(self.target_key, package): repo_contents[package]
             for package in repo_contents},
            aws.s3_buckets[self.target_bucket])

    def test_metadata_uploaded(self):
        """
        Calling :func:`update_repo` uploads metadata for a source repository to
        S3.
        """
        aws = FakeAWS(
            routing_rules={},
            s3_buckets={
                self.target_bucket: {},
            },
        )

        self.update_repo(
            aws=aws,
            yum=FakeYum(),
            rpm_directory=self.rpm_directory,
            target_bucket=self.target_bucket,
            target_key=self.target_key,
            source_repo=self.create_fake_repository(files={}),
            packages=self.packages,
        )

        self.assertIn(
            os.path.join(self.target_key, 'repodata', 'repomd.xml'),
            aws.s3_buckets[self.target_bucket])

    def test_repository_added_to(self):
        """
        Calling :func:`update_repo` does not delete packages which already
        exist in S3.
        """
        existing_s3_keys = {
            os.path.join(self.target_key, 'existing_package.rpm'): '',
        }

        aws = FakeAWS(
            routing_rules={},
            s3_buckets={
                self.target_bucket: existing_s3_keys,
            },
        )

        repo_contents = {
            'clusterhq-flocker-cli-0.3.3-0.dev.7.noarch.rpm': 'cli-package',
            'clusterhq-flocker-node-0.3.3-0.dev.7.noarch.rpm': 'node-package',
        }

        self.update_repo(
            aws=aws,
            yum=FakeYum(),
            rpm_directory=self.rpm_directory,
            target_bucket=self.target_bucket,
            target_key=self.target_key,
            source_repo=self.create_fake_repository(files=repo_contents),
            packages=self.packages,
        )

        expected_keys = existing_s3_keys.copy()
        expected_keys.update({
            os.path.join(self.target_key, package): repo_contents[package]
            for package in repo_contents})

        self.assertDictContainsSubset(
            expected_keys,
            aws.s3_buckets[self.target_bucket])

    def test_packages_updated(self):
        """
        Calling :func:`update_repo` with a source repository containing a
        package when a package already exists on S3 with the same name
        replaces the package on S3 with the one from the source repository.
        """
        cli_package = 'clusterhq-flocker-cli-0.3.3-0.dev.7.noarch.rpm'
        existing_s3_keys = {
            os.path.join(self.target_key, cli_package): 'old-cli-package',
        }

        aws = FakeAWS(
            routing_rules={},
            s3_buckets={
                self.target_bucket: existing_s3_keys.copy(),
            },
        )

        repo_contents = {
            cli_package: 'cli-package',
            'clusterhq-flocker-node-0.3.3-0.dev.7.noarch.rpm': 'node-package',
        }

        self.update_repo(
            aws=aws,
            yum=FakeYum(),
            rpm_directory=self.rpm_directory,
            target_bucket=self.target_bucket,
            target_key=self.target_key,
            source_repo=self.create_fake_repository(files=repo_contents),
            packages=self.packages,
        )

        expected_keys = existing_s3_keys.copy()
        expected_keys.update({
            os.path.join(self.target_key, package): repo_contents[package]
            for package in repo_contents})

        self.assertDictContainsSubset(
            expected_keys,
            aws.s3_buckets[self.target_bucket])

    def test_repository_metadata_index_updated(self):
        """
        Calling :func:`update_repo` updates the repository metadata index.
        """
        index_path = os.path.join(self.target_key, 'repodata', 'repomd.xml')
        existing_s3_keys = {
            index_path: 'old_metadata_index',
        }

        aws = FakeAWS(
            routing_rules={},
            s3_buckets={
                self.target_bucket: existing_s3_keys.copy(),
            },
        )

        self.update_repo(
            aws=aws,
            yum=FakeYum(),
            rpm_directory=self.rpm_directory,
            target_bucket=self.target_bucket,
            target_key=self.target_key,
            source_repo=self.create_fake_repository(files={}),
            packages=self.packages,
        )

        self.assertNotEqual(
            existing_s3_keys[index_path],
            aws.s3_buckets[self.target_bucket][index_path])

    def test_existing_metadata_files_not_uploaded(self):
        """
        Calling :func:`update_repo` does not update repository metadata files
        which are not the index.
        """
        index_path = os.path.join(self.target_key, 'repodata', 'repomd.xml')
        existing_metadata_file = os.path.join(self.target_key, 'repodata',
                                              'filelists.xml.gz')

        existing_s3_keys = {
            index_path: 'old_metadata_index',
            existing_metadata_file: 'old_metadata_content',
        }

        aws = FakeAWS(
            routing_rules={},
            s3_buckets={
                self.target_bucket: existing_s3_keys.copy(),
            },
        )

        self.update_repo(
            aws=aws,
            yum=FakeYum(),
            rpm_directory=self.rpm_directory,
            target_bucket=self.target_bucket,
            target_key=self.target_key,
            source_repo=self.create_fake_repository(files={}),
            packages=self.packages,
        )

        self.assertEqual(
            aws.s3_buckets[self.target_bucket][existing_metadata_file],
            existing_s3_keys[existing_metadata_file])

    def test_new_metadata_files_uploaded(self):
        """
        Calling :func:`update_repo` uploads new repository metadata files to
        S3.
        """
        index_path = os.path.join(self.target_key, 'repodata', 'repomd.xml')
        existing_s3_keys = {
            index_path: 'old_metadata_index',
        }

        aws = FakeAWS(
            routing_rules={},
            s3_buckets={
                self.target_bucket: existing_s3_keys.copy(),
            },
        )

        self.update_repo(
            aws=aws,
            yum=FakeYum(),
            rpm_directory=self.rpm_directory,
            target_bucket=self.target_bucket,
            target_key=self.target_key,
            source_repo=self.create_fake_repository(files={}),
            packages=self.packages,
        )

        repodata_files = [
            key for key in aws.s3_buckets[self.target_bucket] if
            key.startswith(os.path.join(self.target_key, 'repodata'))]

        # What matters is that there is more than just the index.
        self.assertGreater(len(repodata_files), 1)

    def test_create_repository_accounts_for_existing_packages(self):
        """
        Calling :func:`update_repo` uploads new repository metadata files to
        S3 which correspond to packages including those already on S3.
        """
        cli_package = 'clusterhq-flocker-cli-0.3.3-0.dev.7.noarch.rpm'
        existing_s3_keys = {
            os.path.join(self.target_key, cli_package): 'old-cli-package',
        }

        aws = FakeAWS(
            routing_rules={},
            s3_buckets={
                self.target_bucket: {},
                self.alternative_bucket: existing_s3_keys.copy(),
            },
        )

        self.update_repo(
            aws=aws,
            yum=FakeYum(),
            rpm_directory=self.rpm_directory,
            target_bucket=self.target_bucket,
            target_key=self.target_key,
            source_repo=self.create_fake_repository(files={}),
            packages=self.packages,
        )

        self.update_repo(
            aws=aws,
            yum=FakeYum(),
            rpm_directory=self.alternative_package_directory,
            target_bucket=self.alternative_bucket,
            target_key=self.target_key,
            source_repo=self.create_fake_repository(files={}),
            packages=self.packages,
        )

        index_path = os.path.join(self.target_key, 'repodata', 'repomd.xml')
        self.assertNotEqual(
            aws.s3_buckets[self.target_bucket][index_path],
            aws.s3_buckets[self.alternative_bucket][index_path])

    def test_create_repository_accounts_for_new_packages(self):
        """
        Calling :func:`update_repo` uploads new repository metadata files to
        S3 which correspond to packages including those in the source
        repository but not already on S3.
        """
        aws = FakeAWS(
            routing_rules={},
            s3_buckets={
                self.target_bucket: {},
                self.alternative_bucket: {},
            },
        )

        repo_contents = {
            'clusterhq-flocker-cli-0.3.3-0.dev.7.noarch.rpm': 'cli-package',
            'clusterhq-flocker-node-0.3.3-0.dev.7.noarch.rpm': 'node-package',
        }

        self.update_repo(
            aws=aws,
            yum=FakeYum(),
            rpm_directory=self.rpm_directory,
            target_bucket=self.target_bucket,
            target_key=self.target_key,
            source_repo=self.create_fake_repository(files=repo_contents),
            packages=[],
        )

        self.update_repo(
            aws=aws,
            yum=FakeYum(),
            rpm_directory=self.alternative_package_directory,
            target_bucket=self.alternative_bucket,
            target_key=self.target_key,
            source_repo=self.create_fake_repository(files=repo_contents),
            packages=self.packages,
        )

        index_path = os.path.join(self.target_key, 'repodata', 'repomd.xml')
        self.assertNotEqual(
            aws.s3_buckets[self.target_bucket][index_path],
            aws.s3_buckets[self.alternative_bucket][index_path])

    def test_unspecified_packages_in_repository_not_uploaded(self):
        """
        Calling :func:`update_repo` does not upload packages to S3 unless they
        correspond to a package name given in the `packages` parameter.
        """
        existing_s3_keys = {
            os.path.join(self.target_key, 'existing_package.rpm'): '',
        }

        aws = FakeAWS(
            routing_rules={},
            s3_buckets={
                self.target_bucket: existing_s3_keys,
            },
        )

        unspecified_package = 'unspecified-package-0.3.3-0.dev.7.noarch.rpm'
        repo_contents = {
            'clusterhq-flocker-cli-0.3.3-0.dev.7.noarch.rpm': '',
            'clusterhq-flocker-node-0.3.3-0.dev.7.noarch.rpm': '',
            unspecified_package: '',
        }

        self.update_repo(
            aws=aws,
            yum=FakeYum(),
            rpm_directory=self.rpm_directory,
            target_bucket=self.target_bucket,
            target_key=self.target_key,
            source_repo=self.create_fake_repository(files=repo_contents),
            packages=self.packages,
        )

        self.assertNotIn(
            os.path.join(self.target_key, unspecified_package),
            aws.s3_buckets[self.target_bucket])

    def test_development_repositories_created(self):
        """
        Calling :func:`upload_rpms` creates development repositories for
        CentOS 7 and Fedora 20 for a development release.
        """
        aws = FakeAWS(
            routing_rules={},
            s3_buckets={
                self.target_bucket: {},
            },
        )

        repo_contents = {
            'results/omnibus/0.3.3dev7/fedora-20/clusterhq-flocker-cli-0.3.3-0.dev.7.noarch.rpm': '',  # noqa
            'results/omnibus/0.3.3dev7/fedora-20/clusterhq-flocker-node-0.3.3-0.dev.7.noarch.rpm': '',  # noqa
            'results/omnibus/0.3.3dev7/centos-7/clusterhq-flocker-cli-0.3.3-0.dev.7.noarch.rpm': '',  # noqa
            'results/omnibus/0.3.3dev7/centos-7/clusterhq-flocker-node-0.3.3-0.dev.7.noarch.rpm': '',  # noqa

        }

        self.upload_rpms(
            aws=aws,
            yum=FakeYum(),
            scratch_directory=self.scratch_directory,
            target_bucket=self.target_bucket,
            version='0.3.3dev7',
            build_server=self.create_fake_repository(files=repo_contents),
        )

        expected_files = set()
        for operating_system in self.operating_systems:
            for file in [
                'clusterhq-flocker-cli-0.3.3-0.dev.7.noarch.rpm',
                'clusterhq-flocker-node-0.3.3-0.dev.7.noarch.rpm',
                'repodata/repomd.xml',
            ]:
                path = os.path.join(
                    'development',
                    operating_system['distro'],
                    operating_system['version'],
                    operating_system['arch'],
                    file,
                )
                expected_files.add(path)

        files_on_s3 = aws.s3_buckets[self.target_bucket].keys()
        self.assertTrue(expected_files.issubset(set(files_on_s3)))

    def test_marketing_repositories_created(self):
        """
        Calling :func:`upload_rpms` creates marketing repositories for
        CentOS 7 and Fedora 20 for a marketing release.
        """
        aws = FakeAWS(
            routing_rules={},
            s3_buckets={
                self.target_bucket: {},
            },
        )

        repo_contents = {
            'results/omnibus/0.3.3/fedora-20/clusterhq-flocker-cli-0.3.3.noarch.rpm': '',  # noqa
            'results/omnibus/0.3.3/fedora-20/clusterhq-flocker-node-0.3.3.noarch.rpm': '',  # noqa
            'results/omnibus/0.3.3/centos-7/clusterhq-flocker-cli-0.3.3.noarch.rpm': '',  # noqa
            'results/omnibus/0.3.3/centos-7/clusterhq-flocker-node-0.3.3.noarch.rpm': '',  # noqa

        }

        self.upload_rpms(
            aws=aws,
            yum=FakeYum(),
            scratch_directory=self.scratch_directory,
            target_bucket=self.target_bucket,
            version='0.3.3',
            build_server=self.create_fake_repository(files=repo_contents),
        )

        expected_files = set()
        for operating_system in self.operating_systems:
            for file in [
                'clusterhq-flocker-cli-0.3.3.noarch.rpm',
                'clusterhq-flocker-node-0.3.3.noarch.rpm',
                'repodata/repomd.xml',
            ]:
                path = os.path.join(
                    'marketing',
                    operating_system['distro'],
                    operating_system['version'],
                    operating_system['arch'],
                    file,
                )
                expected_files.add(path)

        files_on_s3 = aws.s3_buckets[self.target_bucket].keys()

        self.assertTrue(expected_files.issubset(set(files_on_s3)))

    def test_real_yum_utils(self):
        """
        Calling :func:`update_repo` with real yum utilities creates a
        repository in S3.
        """
        source_repo = FilePath(tempfile.mkdtemp())
        FilePath(__file__).sibling('test-repo').copyTo(source_repo)
        repo_uri = 'file://' + source_repo.path

        aws = FakeAWS(
            routing_rules={},
            s3_buckets={
                self.target_bucket: {},
            },
        )

        class RealYum(object):
            def get_dispatcher(self):
                return yum_dispatcher

        self.update_repo(
            aws=aws,
            yum=RealYum(),
            rpm_directory=self.rpm_directory,
            target_bucket=self.target_bucket,
            target_key=self.target_key,
            source_repo=repo_uri,
            packages=self.packages,
        )

        files = [
            'clusterhq-flocker-cli-0.3.3-0.dev.7.noarch.rpm',
            'clusterhq-flocker-node-0.3.3-0.dev.7.noarch.rpm',
            'repodata/1988e623dfb7204ec981d2a2ab1a38da6c0f742717d184088dd0a0f344f6e89c-filelists.sqlite.bz2',  # noqa
            'repodata/2fb86263316de187636c8949988ab6fd72604329a7300ae490bc091d0d23e69c-other.sqlite.bz2',  # noqa
            'repodata/9bd2f440089b24817e38898e81adba7739b1a904533528819574528698828750-filelists.xml.gz',  # noqa
            'repodata/e8671396d8181102616d45d4916fe74fb886c6f9dfcb62df546e258e830cb11c-other.xml.gz',  # noqa
            'repodata/repomd.xml'
        ]
        expected_files = set([os.path.join(self.target_key, file) for file in
                              files])

        files_on_s3 = aws.s3_buckets[self.target_bucket].keys()
        self.assertTrue(expected_files.issubset(set(files_on_s3)))
