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
from ..yum import FakeYum


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
    def update_repo(self, aws, yum,
                    rpm_directory, target_bucket, target_key, source_repo,
                    packages, version):
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
                        packages, version))

    def setUp(self):
        self.scratch_directory = FilePath(tempfile.mkdtemp(
            prefix=b'test-scratch-directory-'))
        self.rpm_directory = self.scratch_directory.child(b'distro-version-arch')
        self.target_key = 'test/target/key'
        self.source_repo = FilePath(tempfile.mkdtemp())
        self.addCleanup(self.scratch_directory.remove)
        self.target_bucket = 'test-target-bucket'
        self.build_server = 'http://test-build-server.com'
        self.version = '0.3.3dev7'

    def test_upload_non_release_fails(self):
        """
        Trying to upload RPMs for a version that isn't a release fails.
        """
        self.assertRaises(
            NotARelease,
            upload_rpms,
            self.scratch_directory, self.target_bucket, '0.3.0-444-gf05215b',
            self.build_server)

    def test_upload_doc_release_fails(self):
        """
        Trying to upload RPMs for a documentation release fails.
        """
        self.assertRaises(
            DocumentationRelease,
            upload_rpms,
            self.scratch_directory, self.target_bucket, '0.3.0+doc1',
            self.build_server)

    def test_packages_uploaded(self):
        """
        Uploading a repository to an empty bucket puts packages in
        place.
        # TODO test that repodata is put in place
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

        for key in repo_contents:
            self.source_repo.child(key).touch()
            self.source_repo.child(key).setContent(repo_contents[key])

        self.update_repo(
            aws=aws,
            yum=FakeYum(),
            rpm_directory=self.rpm_directory,
            target_bucket=self.target_bucket,
            target_key=self.target_key,
            source_repo='file://' + self.source_repo.path,
            packages=['clusterhq-flocker-cli', 'clusterhq-flocker-node'],
            version=self.version,
        )

        self.assertDictContainsSubset(
            {os.path.join(self.target_key, package): repo_contents[package]
             for package in repo_contents},
            aws.s3_buckets[self.target_bucket])

    def test_real_yum_commands(self):
        pass

    def _test_repository_added_to(self):
        """
        If new packages are added to the repository, old packages remain and
        repodata is modified.
        # TODO second part is not tested
        """
        target_key = 'test/target/key'

        existing_s3_keys = {
            os.path.join(target_key, 'existing_package.rpm'): '',
            os.path.join(target_key, 'repodata', 'repomd.xml'): 'adam',
        }

        aws = FakeAWS(
            routing_rules={},
            s3_buckets={
                self.target_bucket: existing_s3_keys,
            },
        )

        rpm_directory = self.scratch_directory.child(b'distro-version-arch')
        source_repo = FilePath(tempfile.mkdtemp())
        repo_contents = {
            'clusterhq-flocker-cli-0.3.3-0.dev.7.noarch.rpm': 'adam',
            'clusterhq-flocker-node-0.3.3-0.dev.7.noarch.rpm': 'floop',
        }
        # TODO self.update_repo should take this as a dictionary and create
        # a repo
        for key in repo_contents:
            source_repo.child(key).touch()
            source_repo.child(key).setContent(repo_contents[key])

        self.update_repo(
            aws=aws,
            yum=FakeYum(),
            rpm_directory=rpm_directory,
            target_bucket=self.target_bucket,
            target_key=target_key,
            source_repo='file://' + source_repo.path,
            packages=['clusterhq-flocker-cli', 'clusterhq-flocker-node'],
            version='0.3.3dev7',
        )

        repodata_files = {
            'repomd.xml': '',
        }

        expected_keys = {}

        for key in existing_s3_keys:
            expected_keys[key] = existing_s3_keys[key]

        for repodata_file in repodata_files:
            key = os.path.join(target_key, 'repodata', repodata_file)
            content = rpm_directory.child('repodata').child(repodata_file).path
            expected_keys[key] = content

        for package in repo_contents:
            key = os.path.join(target_key, package)
            content = rpm_directory.child(package).path
            expected_keys[key] = content

        self.assertEqual(
            expected_keys, aws.s3_buckets[self.target_bucket])
        # TODO Fill in stub tests

    def test_packages_updated(self):
        """
        If a new version of a package which already exists in S3 is available,
        the old package is replaced.
        """

    def test_development_repositories_created(self):
        """
        upload_rpms creates development repositories for CentOS 7 and Fedora 20
        for a development release.
        """

    def test_marketing_repositories_created(self):
        """
        upload_rpms creates marketing repositories for CentOS 7 and Fedora 20
        for a marketing release.
        """
