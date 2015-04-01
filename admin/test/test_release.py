# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``admin.release``.
"""

import os
from twisted.trial.unittest import SynchronousTestCase as TestCase
from unittest import skipUnless
from effect import sync_perform, ComposedDispatcher, base_dispatcher

from requests.exceptions import HTTPError

from twisted.python.filepath import FilePath
from twisted.python.procutils import which

from ..packaging import Distribution
from ..release import (
    rpm_version, make_rpm_version, upload_rpms, update_repo,
    publish_docs, Environments,
    DocumentationRelease, NotTagged, NotARelease,
)
from ..aws import FakeAWS, CreateCloudFrontInvalidation
from ..yum import FakeYum, yum_dispatcher
from hashlib import sha256


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


class UpdateRepoTests(TestCase):
    """
    Tests for :func:``update_repo``.
    """
    def setUp(self):
        pass
        self.target_bucket = 'test-target-bucket'
        self.target_key = 'test/target/key'
        self.package_directory = FilePath(self.mktemp())

        self.packages = ['clusterhq-flocker-cli', 'clusterhq-flocker-node']

    def update_repo(self, aws, yum,
                    package_directory, target_bucket, target_key, source_repo,
                    packages, flocker_version, distro_name, distro_version):
        """
        Call :func:``update_repo``, interacting with a fake AWS and yum
        utilities.

        :param FakeAWS aws: Fake AWS to interact with.
        :param FakeYum yum: Fake yum utilities to interact with.

        See :py:func:`update_repo` for other parameter documentation.
        """
        dispatchers = [aws.get_dispatcher(), yum.get_dispatcher(),
                       base_dispatcher]
        sync_perform(
            ComposedDispatcher(dispatchers),
            update_repo(
                package_directory=package_directory,
                target_bucket=target_bucket,
                target_key=target_key,
                source_repo=source_repo,
                packages=packages,
                flocker_version=flocker_version,
                distro_name=distro_name,
                distro_version=distro_version,
            )
        )

    def test_fake_rpm(self):
        """
        Calling :func:`update_repo` downloads the new RPMs, creates the
        metadata, and uploads it to S3.

        - Existing package on S3 are preserved in the metadata.
        - Other packages on the buildserver are not downloaded.
        - Existing metadata files are left untouched.
        """
        existing_s3_keys = {
            os.path.join(self.target_key, 'existing_package.rpm'): '',
            os.path.join(self.target_key,
                         'clusterhq-flocker-cli-0.3.3-0.dev.7.noarch.rpm'):
                'existing-content-to-be-replaced',
            os.path.join(self.target_key, 'repodata', 'repomod.xml'):
                '<oldhash>-metadata.xml',
            os.path.join(self.target_key, 'repodata',
                         '<oldhash>-metadata.xml'):
                'metadata for: existing_package.rpm',
        }

        aws = FakeAWS(
            routing_rules={},
            s3_buckets={
                self.target_bucket: existing_s3_keys,
            },
        )

        unspecified_package = 'unspecified-package-0.3.3-0.dev.7.noarch.rpm'
        repo_contents = {
            'clusterhq-flocker-cli-0.3.3-0.dev.7.noarch.rpm': 'cli-package',
            'clusterhq-flocker-node-0.3.3-0.dev.7.noarch.rpm': 'node-package',
            unspecified_package: 'unspecified-package-content',
        }

        self.update_repo(
            aws=aws,
            yum=FakeYum(),
            package_directory=self.package_directory,
            target_bucket=self.target_bucket,
            target_key=self.target_key,
            source_repo=create_fake_repository(self, files=repo_contents),
            packages=self.packages,
            flocker_version='0.3.3dev7',
            distro_name='fedora',
            distro_version='7',
        )

        # The expected files are the new files plus the package which already
        # existed in S3.
        expected_packages = {
            'existing_package.rpm',
            'clusterhq-flocker-cli-0.3.3-0.dev.7.noarch.rpm',
            'clusterhq-flocker-node-0.3.3-0.dev.7.noarch.rpm',
        }

        expected_keys = existing_s3_keys.copy()
        expected_keys.update({
            'test/target/key/clusterhq-flocker-cli-0.3.3-0.dev.7.noarch.rpm':
                'cli-package',
            'test/target/key/clusterhq-flocker-node-0.3.3-0.dev.7.noarch.rpm':
                'node-package',
            })
        expected_keys.update({
            os.path.join(self.target_key, 'repodata', 'repomod.xml'):
                '<newhash>-metadata.xml',
            os.path.join(self.target_key, 'repodata',
                         '<newhash>-metadata.xml'):
                'metadata content for: ' + ','.join(expected_packages),
        })

        self.assertEqual(
            expected_keys,
            aws.s3_buckets[self.target_bucket])

    def test_fake_deb(self):
        """
        Calling :func:`update_repo` downloads the new DEBs, creates the
        metadata, and uploads it to S3.

        - Existing package on S3 are preserved in the metadata.
        - Other packages on the buildserver are not downloaded.
        """
        existing_s3_keys = {
            os.path.join(self.target_key, 'existing_package.deb'): '',
            os.path.join(self.target_key,
                         'clusterhq-flocker-cli_0.3.3-0.dev.7_all.deb'):
                'existing-content-to-be-replaced',
            os.path.join(self.target_key, 'Packages.gz'):
                'metadata for: existing_package.deb',
        }

        aws = FakeAWS(
            routing_rules={},
            s3_buckets={
                self.target_bucket: existing_s3_keys,
            },
        )

        unspecified_package = 'unspecified-package_0.3.3-0.dev.7_all.deb'
        repo_contents = {
            'clusterhq-flocker-cli_0.3.3-0.dev.7_all.deb': 'cli-package',
            'clusterhq-flocker-node_0.3.3-0.dev.7_all.deb': 'node-package',
            unspecified_package: 'unspecified-package-content',
        }

        self.update_repo(
            aws=aws,
            yum=FakeYum(),
            package_directory=self.package_directory,
            target_bucket=self.target_bucket,
            target_key=self.target_key,
            source_repo=create_fake_repository(self, files=repo_contents),
            packages=self.packages,
            flocker_version='0.3.3dev7',
            distro_name='ubuntu',
            distro_version='14.04',
        )

        # The expected files are the new files plus the package which already
        # existed in S3.
        expected_packages = {
            'existing_package.deb',
            'clusterhq-flocker-cli_0.3.3-0.dev.7_all.deb',
            'clusterhq-flocker-node_0.3.3-0.dev.7_all.deb',
        }

        expected_keys = existing_s3_keys.copy()
        expected_keys.update({
            'test/target/key/clusterhq-flocker-cli_0.3.3-0.dev.7_all.deb':
                'cli-package',
            'test/target/key/clusterhq-flocker-node_0.3.3-0.dev.7_all.deb':
                'node-package',
            'test/target/key/Packages.gz':
                'Packages.gz for: ' + ','.join(expected_packages),
            })

        self.assertEqual(
            expected_keys,
            aws.s3_buckets[self.target_bucket])

    def test_package_not_available_exception(self):
        """
        If a requested package is not available in the repository, a 404 error
        is raised.
        """
        aws = FakeAWS(
            routing_rules={},
            s3_buckets={
                self.target_bucket: {},
            },
        )

        with self.assertRaises(HTTPError) as exception:
            self.update_repo(
                aws=aws,
                yum=FakeYum(),
                package_directory=self.package_directory,
                target_bucket=self.target_bucket,
                target_key=self.target_key,
                source_repo=create_fake_repository(
                    self, files={}),
                packages=self.packages,
                flocker_version='0.3.3dev7',
                distro_name='fedora',
                distro_version='7',
            )

        self.assertEqual(404, exception.exception.response.status_code)

    @skipUnless(which('createrepo'),
                "Tests require the ``createrepo`` command.")
    def test_real_yum_utils(self):
        """
        Calling :func:`update_repo` with real yum utilities creates a
        repository in S3.
        """
        source_repo = FilePath(self.mktemp())
        source_repo.createDirectory()

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
            package_directory=self.package_directory,
            target_bucket=self.target_bucket,
            target_key=self.target_key,
            source_repo=repo_uri,
            packages=self.packages,
            flocker_version='0.3.3dev7',
            distro_name='fedora',
            distro_version='7',
        )

        expected_files = {
            os.path.join(self.target_key, file)
            for file in [
                'clusterhq-flocker-cli-0.3.3-0.dev.7.noarch.rpm',
                'clusterhq-flocker-node-0.3.3-0.dev.7.noarch.rpm',
                'repodata/repomd.xml',
            ]
        }
        files_on_s3 = aws.s3_buckets[self.target_bucket]

        repodata_path = os.path.join(self.target_key, 'repodata')

        # Yum repositories prefix metadata files with the sha256 hash
        # of the file. Since these files contain timestamps, we calculate
        # the hash from the file, to determine the expected file names.
        for metadata_file in [
                'other.sqlite.bz2',
                'filelists.xml.gz',
                'primary.xml.gz',
                'filelists.sqlite.bz2',
                'primary.sqlite.bz2',
                'other.xml.gz',
                ]:
            for key in files_on_s3:
                if (key.endswith(metadata_file)
                        and key.startswith(repodata_path)):
                    expected_files.add(
                        os.path.join(
                            repodata_path,
                            sha256(files_on_s3[key]).hexdigest()
                            + '-' + metadata_file)
                    )
                    break
            else:
                expected_files.add(
                    os.path.join(
                        repodata_path, '<missing>-' + metadata_file))

        # The original source repository contains no metadata.
        # This tests that CreateRepo creates the expected metadata files from
        # given RPMs, not that any metadata files are copied.
        self.assertEqual(expected_files, set(files_on_s3.keys()))


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

        See :py:func:`upload_rpms` for other parameter documentation.
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

    def setUp(self):
        self.scratch_directory = FilePath(self.mktemp())
        self.scratch_directory.createDirectory()
        self.target_bucket = 'test-target-bucket'
        self.build_server = 'http://test-build-server.example'
        self.alternative_bucket = 'bucket-with-existing-package'
        alt_scratch_directory = FilePath(self.mktemp())
        alt_scratch_directory.createDirectory()
        self.alternative_package_directory = alt_scratch_directory.child(
            b'distro-version-arch')
        self.operating_systems = [
            Distribution(name='fedora', version='20'),
            Distribution(name='centos', version='7'),
            Distribution(name='ubuntu', version='14.04'),
        ]
        self.repo_contents = {
            'clusterhq-flocker-cli-0.3.3-0.dev.7.noarch.rpm': 'cli-package',
            'clusterhq-flocker-node-0.3.3-0.dev.7.noarch.rpm': 'node-package',
        }

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
            self.scratch_directory, self.target_bucket, '0.3.0-444-gf05215b',
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
            self.scratch_directory, self.target_bucket, '0.3.0+doc1',
            self.build_server)

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
            'results/omnibus/0.3.3dev7/fedora-20/clusterhq-python-flocker-0.3.3-0.dev.7.x86_64.rpm': '',  # noqa
            'results/omnibus/0.3.3dev7/centos-7/clusterhq-flocker-cli-0.3.3-0.dev.7.noarch.rpm': '',  # noqa
            'results/omnibus/0.3.3dev7/centos-7/clusterhq-flocker-node-0.3.3-0.dev.7.noarch.rpm': '',  # noqa
            'results/omnibus/0.3.3dev7/centos-7/clusterhq-python-flocker-0.3.3-0.dev.7.x86_64.rpm': '',  # noqa
            'results/omnibus/0.3.3dev7/ubuntu-14.04/clusterhq-flocker-cli_0.3.3-0.dev.7_all.deb': '',  # noqa
            'results/omnibus/0.3.3dev7/ubuntu-14.04/clusterhq-flocker-node_0.3.3-0.dev.7_all.deb': '',  # noqa
            'results/omnibus/0.3.3dev7/ubuntu-14.04/clusterhq-python-flocker_0.3.3-0.dev.7_amd64.deb': '',  # noqa
        }

        self.upload_rpms(
            aws=aws,
            yum=FakeYum(),
            scratch_directory=self.scratch_directory,
            target_bucket=self.target_bucket,
            version='0.3.3dev7',
            build_server=create_fake_repository(self, files=repo_contents),
        )

        expected_files = {
            'fedora-testing/20/x86_64/clusterhq-flocker-cli-0.3.3-0.dev.7.noarch.rpm',  # noqa
            'fedora-testing/20/x86_64/clusterhq-flocker-node-0.3.3-0.dev.7.noarch.rpm',  # noqa
            'fedora-testing/20/x86_64/clusterhq-python-flocker-0.3.3-0.dev.7.x86_64.rpm',  # noqa
            'fedora-testing/20/x86_64/repodata/repomod.xml',
            'fedora-testing/20/x86_64/repodata/<newhash>-metadata.xml',
            'centos-testing/7/x86_64/clusterhq-flocker-cli-0.3.3-0.dev.7.noarch.rpm',  # noqa
            'centos-testing/7/x86_64/clusterhq-flocker-node-0.3.3-0.dev.7.noarch.rpm',  # noqa
            'centos-testing/7/x86_64/clusterhq-python-flocker-0.3.3-0.dev.7.x86_64.rpm',  # noqa
            'centos-testing/7/x86_64/repodata/repomod.xml',
            'centos-testing/7/x86_64/repodata/<newhash>-metadata.xml',
            'ubuntu-testing/14.04/amd64/clusterhq-flocker-cli_0.3.3-0.dev.7_all.deb',  # noqa
            'ubuntu-testing/14.04/amd64/clusterhq-flocker-node_0.3.3-0.dev.7_all.deb',  # noqa
            'ubuntu-testing/14.04/amd64/clusterhq-python-flocker_0.3.3-0.dev.7_amd64.deb',  # noqa
            'ubuntu-testing/14.04/amd64/Packages.gz',
            'ubuntu-testing/14.04/amd64/Release',
        }

        files_on_s3 = aws.s3_buckets[self.target_bucket].keys()
        self.assertEqual(expected_files, set(files_on_s3))

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
            'results/omnibus/0.3.3/fedora-20/clusterhq-flocker-cli-0.3.3-1.noarch.rpm': '',  # noqa
            'results/omnibus/0.3.3/fedora-20/clusterhq-flocker-node-0.3.3-1.noarch.rpm': '',  # noqa
            'results/omnibus/0.3.3/fedora-20/clusterhq-python-flocker-0.3.3-1.x86_64.rpm': '',  # noqa
            'results/omnibus/0.3.3/centos-7/clusterhq-flocker-cli-0.3.3-1.noarch.rpm': '',  # noqa
            'results/omnibus/0.3.3/centos-7/clusterhq-flocker-node-0.3.3-1.noarch.rpm': '',  # noqa
            'results/omnibus/0.3.3/centos-7/clusterhq-python-flocker-0.3.3-1.x86_64.rpm': '',  # noqa
            'results/omnibus/0.3.3/ubuntu-14.04/clusterhq-flocker-cli_0.3.3-1_all.deb': '',  # noqa
            'results/omnibus/0.3.3/ubuntu-14.04/clusterhq-flocker-node_0.3.3-1_all.deb': '',  # noqa
            'results/omnibus/0.3.3/ubuntu-14.04/clusterhq-python-flocker_0.3.3-1_amd64.deb': '',  # noqa
        }

        self.upload_rpms(
            aws=aws,
            yum=FakeYum(),
            scratch_directory=self.scratch_directory,
            target_bucket=self.target_bucket,
            version='0.3.3',
            build_server=create_fake_repository(self, files=repo_contents),
        )

        expected_files = {
            'fedora/20/x86_64/clusterhq-flocker-cli-0.3.3-1.noarch.rpm',
            'fedora/20/x86_64/clusterhq-flocker-node-0.3.3-1.noarch.rpm',
            'fedora/20/x86_64/clusterhq-python-flocker-0.3.3-1.x86_64.rpm',
            'fedora/20/x86_64/repodata/repomod.xml',
            'fedora/20/x86_64/repodata/<newhash>-metadata.xml',
            'centos/7/x86_64/clusterhq-flocker-cli-0.3.3-1.noarch.rpm',
            'centos/7/x86_64/clusterhq-flocker-node-0.3.3-1.noarch.rpm',
            'centos/7/x86_64/clusterhq-python-flocker-0.3.3-1.x86_64.rpm',
            'centos/7/x86_64/repodata/repomod.xml',
            'centos/7/x86_64/repodata/<newhash>-metadata.xml',
            'ubuntu/14.04/amd64/clusterhq-flocker-cli_0.3.3-1_all.deb',
            'ubuntu/14.04/amd64/clusterhq-flocker-node_0.3.3-1_all.deb',
            'ubuntu/14.04/amd64/clusterhq-python-flocker_0.3.3-1_amd64.deb',
            'ubuntu/14.04/amd64/Packages.gz',
            'ubuntu/14.04/amd64/Release',
        }

        files_on_s3 = aws.s3_buckets[self.target_bucket].keys()
        self.assertEqual(expected_files, set(files_on_s3))


def create_fake_repository(test_case, files):
    """
    Create files in a directory to mimic a repository of packages.

    :param dict source_repo: Dictionary mapping names of files to create to
        contents.
    :return: FilePath of directory containing fake package files.
    """
    source_repo = FilePath(test_case.mktemp())
    source_repo.createDirectory
    for key in files:
        new_file = source_repo.preauthChild(key)
        if not new_file.parent().exists():
            new_file.parent().makedirs()
        new_file.setContent(files[key])
    return 'file://' + source_repo.path
