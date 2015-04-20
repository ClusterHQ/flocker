# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``admin.release``.
"""

import os
from unittest import skipUnless
import tempfile

from effect import sync_perform, ComposedDispatcher, base_dispatcher
from git import Repo

from requests.exceptions import HTTPError

from twisted.python.filepath import FilePath
from twisted.python.procutils import which
from twisted.python.usage import UsageError
from twisted.trial.unittest import SynchronousTestCase

from ..release import (
    upload_rpms, update_repo,
    publish_docs, Environments, DOCUMENTATION_CONFIGURATIONS,
    DocumentationRelease, NotTagged, NotARelease,
    calculate_base_branch, create_release_branch,
    CreateReleaseBranchOptions, BranchExists, TagExists,
    BaseBranchDoesNotExist, MissingPreRelease, NoPreRelease,
)

from ..aws import FakeAWS, CreateCloudFrontInvalidation
from ..yum import FakeYum, yum_dispatcher


class PublishDocsTests(SynchronousTestCase):
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

    def test_publish_to_doc_version(self):
        """
        Trying to publish to a documentation version in a staging environment
        publishes to to the version being updated.
        """
        aws = FakeAWS(
            routing_rules={
                'clusterhq-staging-docs': {
                    'en/latest/': '',
                },
            },
            s3_buckets={
                'clusterhq-staging-docs': {},
                'clusterhq-dev-docs': {},
            })

        self.publish_docs(
            aws, '0.3.1-444-gf05215b', '0.3.1+doc1',
            environment=Environments.STAGING)

        self.assertEqual(
            aws.routing_rules, {
                'clusterhq-staging-docs': {
                    'en/latest/': 'en/0.3.1/',
                },
            })

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

    def test_production_can_publish_prerelease(self):
        """
        Publishing a pre-release succeeds.
        """
        aws = FakeAWS(
            routing_rules={
                'clusterhq-docs': {
                    'en/devel/': 'en/0.3.1.dev4/',
                },
            },
            s3_buckets={
                'clusterhq-docs': {},
                'clusterhq-dev-docs': {},
            })
        # Does not raise:
        self.publish_docs(
            aws, '0.3.2pre1', '0.3.2pre1', environment=Environments.PRODUCTION)

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

    def assert_error_key_update(self, doc_version, environment, should_update):
        """
        Call ``publish_docs`` and assert that only the expected buckets have an
        updated error_key property.

        :param unicode doc_version: The version of the documentation that is
            being published.
        :param NamedConstant environment: One of the ``NamedConstants`` in
            ``Environments``.
        :param bool should_update: A flag indicating whether the error_key for
            the bucket associated with ``environment`` is expected to be
            updated.
        :raises: ``FailTest`` if an error_key in any of the S3 buckets has been
            updated unexpectedly.
        """
        # Get a set of all target S3 buckets.
        bucket_names = set()
        for e in Environments.iterconstants():
            bucket_names.add(
                DOCUMENTATION_CONFIGURATIONS[e].documentation_bucket
            )
        # Pretend that both devel and latest aliases are currently pointing to
        # an older version.
        empty_routes = {
            'en/devel/': 'en/0.0.0/',
            'en/latest/': 'en/0.0.0/',
        }
        # In all the S3 buckets.
        empty_routing_rules = {
            bucket_name: empty_routes.copy()
            for bucket_name in bucket_names
        }
        # And that all the buckets themselves are empty.
        empty_buckets = {bucket_name: {} for bucket_name in bucket_names}
        # Including the dev bucket
        empty_buckets['clusterhq-dev-docs'] = {}
        # And that all the buckets have an empty error_key
        empty_error_keys = {bucket_name: b'' for bucket_name in bucket_names}

        aws = FakeAWS(
            routing_rules=empty_routing_rules,
            s3_buckets=empty_buckets,
            error_key=empty_error_keys
        )
        # The value of any updated error_key will include the version that's
        # being published.
        expected_error_path = 'en/{}/error_pages/404.html'.format(doc_version)
        expected_updated_bucket = (
            DOCUMENTATION_CONFIGURATIONS[environment].documentation_bucket
        )
        # Grab a copy of the current error_key before it gets mutated.
        expected_error_keys = aws.error_key.copy()
        if should_update:
            # And if an error_key is expected to be updated we expect it to be
            # for the bucket corresponding to the environment that we're
            # publishing to.
            expected_error_keys[expected_updated_bucket] = expected_error_path

        self.publish_docs(
            aws,
            flocker_version=doc_version,
            doc_version=doc_version,
            environment=environment
        )

        self.assertEqual(expected_error_keys, aws.error_key)

    def test_error_key_dev_staging(self):
        """
        Publishing documentation for a development release to the staging
        bucket, updates the error_key in that bucket only.
        """
        self.assert_error_key_update(
            doc_version='0.4.1dev1',
            environment=Environments.STAGING,
            should_update=True
        )

    def test_error_key_dev_production(self):
        """
        Publishing documentation for a development release to the production
        bucket, does not update the error_key in any of the buckets.
        """
        self.assert_error_key_update(
            doc_version='0.4.1dev1',
            environment=Environments.PRODUCTION,
            should_update=False
        )

    def test_error_key_pre_staging(self):
        """
        Publishing documentation for a pre-release to the staging
        bucket, updates the error_key in that bucket only.
        """
        self.assert_error_key_update(
            doc_version='0.4.1pre1',
            environment=Environments.STAGING,
            should_update=True
        )

    def test_error_key_pre_production(self):
        """
        Publishing documentation for a pre-release to the production
        bucket, does not update the error_key in any of the buckets.
        """
        self.assert_error_key_update(
            doc_version='0.4.1pre1',
            environment=Environments.PRODUCTION,
            should_update=False
        )

    def test_error_key_marketing_staging(self):
        """
        Publishing documentation for a marketing release to the staging
        bucket, updates the error_key in that bucket.
        """
        self.assert_error_key_update(
            doc_version='0.4.1',
            environment=Environments.STAGING,
            should_update=True
        )

    def test_error_key_marketing_production(self):
        """
        Publishing documentation for a marketing release to the production
        bucket, updates the error_key in that bucket.
        """
        self.assert_error_key_update(
            doc_version='0.4.1',
            environment=Environments.PRODUCTION,
            should_update=True
        )


class UploadRPMsTests(SynchronousTestCase):
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

    def update_repo(self, aws, yum,
                    rpm_directory, target_bucket, target_key, source_repo,
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
                rpm_directory=rpm_directory,
                target_bucket=target_bucket,
                target_key=target_key,
                source_repo=source_repo,
                packages=packages,
                flocker_version=flocker_version,
                distro_name=distro_name,
                distro_version=distro_version,
            )
        )

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
        self.build_server = 'http://test-build-server.example'
        # clusterhq-python-flocker is not here because for the tests which use
        # real RPMs, it would be bad to have to have that large package.
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
        self.dev_version = '0.3.3dev7'
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

        self.update_repo(
            aws=aws,
            yum=FakeYum(),
            rpm_directory=self.rpm_directory,
            target_bucket=self.target_bucket,
            target_key=self.target_key,
            source_repo=self.create_fake_repository(files=self.repo_contents),
            packages=self.packages,
            flocker_version=self.dev_version,
            distro_name=self.operating_systems[0]['distro'],
            distro_version=self.operating_systems[0]['version'],
        )

        self.assertDictContainsSubset(
            {os.path.join(self.target_key, package):
                self.repo_contents[package]
             for package in self.repo_contents},
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
            source_repo=self.create_fake_repository(files=self.repo_contents),
            packages=self.packages,
            flocker_version=self.dev_version,
            distro_name=self.operating_systems[0]['distro'],
            distro_version=self.operating_systems[0]['version'],
        )

        self.assertIn(
            os.path.join(self.target_key, 'repodata', 'repomd.xml'),
            aws.s3_buckets[self.target_bucket])

    def test_repository_added_to(self):
        """
        Calling :func:`update_repo` does not delete packages or metadata which
        already exist in S3.
        """
        existing_s3_keys = {
            os.path.join(self.target_key, 'existing_package.rpm'): '',
            os.path.join(self.target_key, 'repodata', 'existing_metadata.xml'):
                '',
        }

        aws = FakeAWS(
            routing_rules={},
            s3_buckets={
                self.target_bucket: existing_s3_keys,
            },
        )

        self.update_repo(
            aws=aws,
            yum=FakeYum(),
            rpm_directory=self.rpm_directory,
            target_bucket=self.target_bucket,
            target_key=self.target_key,
            source_repo=self.create_fake_repository(files=self.repo_contents),
            packages=self.packages,
            flocker_version=self.dev_version,
            distro_name=self.operating_systems[0]['distro'],
            distro_version=self.operating_systems[0]['version'],
        )

        # The expected files are the new files plus the package which already
        # existed in S3.
        expected_keys = existing_s3_keys.copy()
        expected_keys.update({
            os.path.join(self.target_key, package): self.repo_contents[package]
            for package in self.repo_contents})

        self.assertDictContainsSubset(
            expected_keys,
            aws.s3_buckets[self.target_bucket])

    def test_packages_updated(self):
        """
        Calling :func:`update_repo` with a source repository containing a
        package when a package already exists on S3 with the same name
        replaces the package on S3 with the one from the source repository.
        """
        existing_package_name = self.repo_contents.keys()[0]
        existing_s3_keys = {
            os.path.join(self.target_key, existing_package_name):
                'existing-content-to-be-replaced',
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
            source_repo=self.create_fake_repository(files=self.repo_contents),
            packages=self.packages,
            flocker_version=self.dev_version,
            distro_name=self.operating_systems[0]['distro'],
            distro_version=self.operating_systems[0]['version'],
        )

        expected_keys = existing_s3_keys.copy()
        expected_keys.update({
            os.path.join(self.target_key, package): self.repo_contents[package]
            for package in self.repo_contents})

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
            source_repo=self.create_fake_repository(files=self.repo_contents),
            packages=self.packages,
            flocker_version=self.dev_version,
            distro_name=self.operating_systems[0]['distro'],
            distro_version=self.operating_systems[0]['version'],
        )

        self.assertNotEqual(
            existing_s3_keys[index_path],
            aws.s3_buckets[self.target_bucket][index_path])

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
            source_repo=self.create_fake_repository(files=self.repo_contents),
            packages=self.packages,
            flocker_version=self.dev_version,
            distro_name=self.operating_systems[0]['distro'],
            distro_version=self.operating_systems[0]['version'],
        )

        repodata_files = [
            key[len(self.target_key) + len('/repodata/'):] for key in
            aws.s3_buckets[self.target_bucket] if
            key.startswith(os.path.join(self.target_key, 'repodata'))]

        # The hashes used in the fake aren't going to be the same as the
        # hashes in the real implementation. What matters is that they change
        # depending on the package names.
        expected_repodata = [
            'aa56424de4246c734dd2ed9b2fd14152-primary.xml.gz',
            '90ea647eafe44d1479109c1c4093ab48-other.xml.gz',
            'repomd.xml',
            '3d4791a418739c1bb3f025423f2f5896-filelists.xml.gz',
        ]
        self.assertEqual(sorted(repodata_files), sorted(expected_repodata))

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
            source_repo=self.create_fake_repository(files=self.repo_contents),
            packages=[],
            flocker_version=self.dev_version,
            distro_name=self.operating_systems[0]['distro'],
            distro_version=self.operating_systems[0]['version'],
        )

        self.update_repo(
            aws=aws,
            yum=FakeYum(),
            rpm_directory=self.alternative_package_directory,
            target_bucket=self.alternative_bucket,
            target_key=self.target_key,
            source_repo=self.create_fake_repository(files={}),
            packages=[],
            flocker_version=self.dev_version,
            distro_name=self.operating_systems[0]['distro'],
            distro_version=self.operating_systems[0]['version'],
        )

        index_path = os.path.join(self.target_key, 'repodata', 'repomd.xml')
        # There are two buckets. One had existing packages on S3. One had
        # no existing packages on S3. This tests that the repository metadata
        # index is different for each of these buckets.
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

        self.update_repo(
            aws=aws,
            yum=FakeYum(),
            rpm_directory=self.rpm_directory,
            target_bucket=self.target_bucket,
            target_key=self.target_key,
            source_repo=self.create_fake_repository(files=self.repo_contents),
            packages=[],
            flocker_version=self.dev_version,
            distro_name=self.operating_systems[0]['distro'],
            distro_version=self.operating_systems[0]['version'],
        )

        self.update_repo(
            aws=aws,
            yum=FakeYum(),
            rpm_directory=self.alternative_package_directory,
            target_bucket=self.alternative_bucket,
            target_key=self.target_key,
            source_repo=self.create_fake_repository(files=self.repo_contents),
            packages=self.packages,
            flocker_version=self.dev_version,
            distro_name=self.operating_systems[0]['distro'],
            distro_version=self.operating_systems[0]['version'],
        )

        index_path = os.path.join(self.target_key, 'repodata', 'repomd.xml')
        # The index contains details about the new packages in the repository
        # which has those new packages. The other repository has no packages
        # and so the index is different.
        self.assertNotEqual(
            aws.s3_buckets[self.target_bucket][index_path],
            aws.s3_buckets[self.alternative_bucket][index_path])

    def test_unspecified_packages_in_repository_not_uploaded(self):
        """
        Calling :func:`update_repo` does not upload packages to S3 unless they
        correspond to a package name given in the `packages` parameter.
        """
        aws = FakeAWS(
            routing_rules={},
            s3_buckets={
                self.target_bucket: {},
            },
        )

        unspecified_package = 'unspecified-package-0.3.3-0.dev.7.noarch.rpm'
        self.repo_contents[unspecified_package] = 'unspecified-package-content'

        self.update_repo(
            aws=aws,
            yum=FakeYum(),
            rpm_directory=self.rpm_directory,
            target_bucket=self.target_bucket,
            target_key=self.target_key,
            source_repo=self.create_fake_repository(files=self.repo_contents),
            packages=self.packages,
            flocker_version=self.dev_version,
            distro_name=self.operating_systems[0]['distro'],
            distro_version=self.operating_systems[0]['version'],
        )

        self.assertNotIn(
            os.path.join(self.target_key, unspecified_package),
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

        # The repo contents will be missing one item from self.packages
        self.repo_contents.pop(self.repo_contents.keys()[0])

        with self.assertRaises(HTTPError) as exception:
            self.update_repo(
                aws=aws,
                yum=FakeYum(),
                rpm_directory=self.rpm_directory,
                target_bucket=self.target_bucket,
                target_key=self.target_key,
                source_repo=self.create_fake_repository(
                    files=self.repo_contents),
                packages=self.packages,
                flocker_version=self.dev_version,
                distro_name=self.operating_systems[0]['distro'],
                distro_version=self.operating_systems[0]['version'],
            )

        self.assertEqual(404, exception.exception.response.status_code)

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
        }

        self.upload_rpms(
            aws=aws,
            yum=FakeYum(),
            scratch_directory=self.scratch_directory,
            target_bucket=self.target_bucket,
            version=self.dev_version,
            build_server=self.create_fake_repository(files=repo_contents),
        )

        expected_files = [
            'centos-testing/7/x86_64/clusterhq-flocker-cli-0.3.3-0.dev.7.noarch.rpm',  # noqa
            'centos-testing/7/x86_64/clusterhq-flocker-node-0.3.3-0.dev.7.noarch.rpm',  # noqa
            'centos-testing/7/x86_64/clusterhq-python-flocker-0.3.3-0.dev.7.x86_64.rpm',  # noqa
            'centos-testing/7/x86_64/repodata/3d4791a418739c1bb3f025423f2f5896-filelists.xml.gz',  # noqa
            'centos-testing/7/x86_64/repodata/90ea647eafe44d1479109c1c4093ab48-other.xml.gz',  # noqa
            'centos-testing/7/x86_64/repodata/aa56424de4246c734dd2ed9b2fd14152-primary.xml.gz',  # noqa
            'centos-testing/7/x86_64/repodata/repomd.xml',
            'fedora-testing/20/x86_64/clusterhq-flocker-cli-0.3.3-0.dev.7.noarch.rpm',  # noqa
            'fedora-testing/20/x86_64/clusterhq-flocker-node-0.3.3-0.dev.7.noarch.rpm',  # noqa
            'fedora-testing/20/x86_64/clusterhq-python-flocker-0.3.3-0.dev.7.x86_64.rpm',  # noqa
            'fedora-testing/20/x86_64/repodata/3d4791a418739c1bb3f025423f2f5896-filelists.xml.gz',  # noqa
            'fedora-testing/20/x86_64/repodata/90ea647eafe44d1479109c1c4093ab48-other.xml.gz',  # noqa
            'fedora-testing/20/x86_64/repodata/aa56424de4246c734dd2ed9b2fd14152-primary.xml.gz',  # noqa
            'fedora-testing/20/x86_64/repodata/repomd.xml',
    ]

        self.assertEqual(
            sorted(expected_files),
            sorted(aws.s3_buckets[self.target_bucket].keys()))

    def test_development_repositories_created_for_pre_release(self):
        """
        Calling :func:`upload_rpms` creates development repositories for
        CentOS 7 and Fedora 20 for a pre-release.
        """
        aws = FakeAWS(
            routing_rules={},
            s3_buckets={
                self.target_bucket: {},
            },
        )

        repo_contents = {
            'results/omnibus/0.3.0pre1/fedora-20/clusterhq-flocker-cli-0.3.0-0.pre.1.noarch.rpm': '',  # noqa
            'results/omnibus/0.3.0pre1/fedora-20/clusterhq-flocker-node-0.3.0-0.pre.1.noarch.rpm': '',  # noqa
            'results/omnibus/0.3.0pre1/fedora-20/clusterhq-python-flocker-0.3.0-0.pre.1.x86_64.rpm': '',  # noqa
            'results/omnibus/0.3.0pre1/centos-7/clusterhq-flocker-cli-0.3.0-0.pre.1.noarch.rpm': '',  # noqa
            'results/omnibus/0.3.0pre1/centos-7/clusterhq-flocker-node-0.3.0-0.pre.1.noarch.rpm': '',  # noqa
            'results/omnibus/0.3.0pre1/centos-7/clusterhq-python-flocker-0.3.0-0.pre.1.x86_64.rpm': '',  # noqa
        }

        self.upload_rpms(
            aws=aws,
            yum=FakeYum(),
            scratch_directory=self.scratch_directory,
            target_bucket=self.target_bucket,
            version='0.3.0pre1',
            build_server=self.create_fake_repository(files=repo_contents),
        )

        expected_files = [
            'fedora-testing/20/x86_64/repodata/3d4791a418739c1bb3f025423f2f5896-filelists.xml.gz',  # noqa
            'centos-testing/7/x86_64/clusterhq-python-flocker-0.3.0-0.pre.1.x86_64.rpm',  # noqa
            'fedora-testing/20/x86_64/clusterhq-flocker-node-0.3.0-0.pre.1.noarch.rpm',  # noqa
            'centos-testing/7/x86_64/repodata/aa56424de4246c734dd2ed9b2fd14152-primary.xml.gz',  # noqa
            'fedora-testing/20/x86_64/clusterhq-python-flocker-0.3.0-0.pre.1.x86_64.rpm',  # noqa
            'fedora-testing/20/x86_64/clusterhq-flocker-cli-0.3.0-0.pre.1.noarch.rpm',  # noqa
            'fedora-testing/20/x86_64/repodata/aa56424de4246c734dd2ed9b2fd14152-primary.xml.gz',  # noqa
            'fedora-testing/20/x86_64/repodata/90ea647eafe44d1479109c1c4093ab48-other.xml.gz',  # noqa
            'centos-testing/7/x86_64/repodata/90ea647eafe44d1479109c1c4093ab48-other.xml.gz',  # noqa
            'centos-testing/7/x86_64/clusterhq-flocker-cli-0.3.0-0.pre.1.noarch.rpm',  # noqa
            'centos-testing/7/x86_64/clusterhq-flocker-node-0.3.0-0.pre.1.noarch.rpm',  # noqa
            'centos-testing/7/x86_64/repodata/repomd.xml',
            'centos-testing/7/x86_64/repodata/3d4791a418739c1bb3f025423f2f5896-filelists.xml.gz',  # noqa
            'fedora-testing/20/x86_64/repodata/repomd.xml',
        ]

        self.assertEqual(
            sorted(expected_files),
            sorted(aws.s3_buckets[self.target_bucket].keys()))


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
        }

        self.upload_rpms(
            aws=aws,
            yum=FakeYum(),
            scratch_directory=self.scratch_directory,
            target_bucket=self.target_bucket,
            version='0.3.3',
            build_server=self.create_fake_repository(files=repo_contents),
        )

        expected_files = [
            'centos/7/x86_64/repodata/3d4791a418739c1bb3f025423f2f5896-filelists.xml.gz',  # noqa
            'centos/7/x86_64/repodata/90ea647eafe44d1479109c1c4093ab48-other.xml.gz',  # noqa
            'fedora/20/x86_64/repodata/3d4791a418739c1bb3f025423f2f5896-filelists.xml.gz',  # noqa
            'centos/7/x86_64/repodata/repomd.xml',
            'centos/7/x86_64/clusterhq-python-flocker-0.3.3-1.x86_64.rpm',
            'fedora/20/x86_64/clusterhq-python-flocker-0.3.3-1.x86_64.rpm',
            'fedora/20/x86_64/repodata/aa56424de4246c734dd2ed9b2fd14152-primary.xml.gz',  # noqa
            'fedora/20/x86_64/clusterhq-flocker-cli-0.3.3-1.noarch.rpm',
            'fedora/20/x86_64/repodata/repomd.xml',
            'centos/7/x86_64/clusterhq-flocker-node-0.3.3-1.noarch.rpm',
            'centos/7/x86_64/repodata/aa56424de4246c734dd2ed9b2fd14152-primary.xml.gz',  # noqa
            'fedora/20/x86_64/repodata/90ea647eafe44d1479109c1c4093ab48-other.xml.gz',  # noqa
            'centos/7/x86_64/clusterhq-flocker-cli-0.3.3-1.noarch.rpm',
            'fedora/20/x86_64/clusterhq-flocker-node-0.3.3-1.noarch.rpm',
         ]

        self.assertEqual(
            sorted(expected_files),
            sorted(aws.s3_buckets[self.target_bucket].keys()))

    @skipUnless(which('createrepo'),
        "Tests require the ``createrepo`` command.")
    def test_real_yum_utils(self):
        """
        Calling :func:`update_repo` with real yum utilities creates a
        repository in S3.
        """
        source_repo = FilePath(tempfile.mkdtemp())
        self.addCleanup(source_repo.remove)

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
            flocker_version=self.dev_version,
            distro_name=self.operating_systems[0]['distro'],
            distro_version=self.operating_systems[0]['version'],
        )

        files = [
            'repodata/e8671396d8181102616d45d4916fe74fb886c6f9dfcb62df546e258e830cb11c-other.xml.gz', # noqa
            'clusterhq-flocker-cli-0.3.3-0.dev.7.noarch.rpm',
            'repodata/repomd.xml',
            'clusterhq-flocker-node-0.3.3-0.dev.7.noarch.rpm',
            'repodata/9bd2f440089b24817e38898e81adba7739b1a904533528819574528698828750-filelists.xml.gz',  # noqa
            'repodata/9bfa6161e98d5b438cf360853cc0366e4909909b4e7897ced63443611befbbe5-filelists.sqlite.bz2',  # noqa
            'repodata/f497f27e365c8be8f3ca0689b15030a5f5be94ec61caad1f55b7bd1cc8707355-other.sqlite.bz2'  # noqa
        ]
        expected_files = set([os.path.join(self.target_key, file) for file in
                              files])

        files_on_s3 = aws.s3_buckets[self.target_bucket].keys()

        self.assertTrue(
            expected_files.issubset(set(files_on_s3)),
            "Metadata files for the packages were not created.")


class CreateReleaseBranchOptionsTests(SynchronousTestCase):
    """
    Tests for :class:`CreateReleaseBranchOptions`.
    """

    def test_flocker_version_required(self):
          """
          The ``--flocker-version`` option is required.
          """
          options = CreateReleaseBranchOptions()
          self.assertRaises(
              UsageError,
              options.parseOptions, [])


def create_git_repository(test_case):
    """
    Create a git repository with a ``master`` branch and ``README``.

    :param test_case: The ``TestCase`` calling this.
    """
    directory = FilePath(test_case.mktemp())
    directory.child('README').makedirs()
    directory.child('README').touch()

    repository = Repo.init(path=directory.path)
    repository.index.add(['README'])
    repository.index.commit('Initial commit')
    repository.create_head('master')
    return repository


class CreateReleaseBranchTests(SynchronousTestCase):
    """
    Tests for :func:`create_release_branch`.
    """
    def setUp(self):
        self.repo = create_git_repository(test_case=self)

    def test_branch_exists_fails(self):
        """
        Trying to create a release when a branch already exists for the given
        version fails.
        """
        branch = self.repo.create_head('release/flocker-0.3.0')

        self.assertRaises(
            BranchExists,
            create_release_branch, '0.3.0', base_branch=branch)

    def test_active_branch(self):
        """
        Creating a release branch changes the active branch on the given
        branch's repository.
        """
        branch = self.repo.create_head('release/flocker-0.3.0pre1')

        create_release_branch(version='0.3.0', base_branch=branch)
        self.assertEqual(
            self.repo.active_branch.name,
            "release/flocker-0.3.0")

    def test_branch_created_from_base(self):
        """
        The new branch is created from the given branch.
        """
        master = self.repo.active_branch
        branch = self.repo.create_head('release/flocker-0.3.0pre1')
        branch.checkout()
        FilePath(self.repo.working_dir).child('NEW_FILE').touch()
        self.repo.index.add(['NEW_FILE'])
        self.repo.index.commit('Add NEW_FILE')
        master.checkout()
        create_release_branch(version='0.3.0', base_branch=branch)
        self.assertIn((u'NEW_FILE', 0), self.repo.index.entries)


class CalculateBaseBranchTests(SynchronousTestCase):
    """
    Tests for :func:`calculate_base_branch`.
    """

    def setUp(self):
        self.repo = create_git_repository(test_case=self)

    def calculate_base_branch(self, version):
        return calculate_base_branch(
            version=version, path=self.repo.working_dir)

    def test_calculate_base_branch_for_non_release_fails(self):
        """
        Calling :func:`calculate_base_branch` with a version that isn't a
        release fails.
        """
        self.assertRaises(
            NotARelease,
            self.calculate_base_branch, '0.3.0-444-gf05215b')

    def test_weekly_release_base(self):
        """
        A weekly release is created from the "master" branch.
        """
        self.assertEqual(
            self.calculate_base_branch(version='0.3.0dev1').name,
            "master")

    def test_doc_release_base(self):
        """
        A documentation release is created from the release which is having
        its documentation changed.
        """
        self.repo.create_head('release/flocker-0.3.0')
        self.assertEqual(
            self.calculate_base_branch(version='0.3.0+doc1').name,
            "release/flocker-0.3.0")

    def test_first_pre_release(self):
        """
        The first pre-release for a marketing release is created from the
        "master" branch.
        """
        self.assertEqual(
            self.calculate_base_branch(version='0.3.0pre1').name,
            "master")

    def test_uses_previous_pre_release(self):
        """
        The second pre-release for a marketing release is created from the
        previous pre-release release branch.
        """
        self.repo.create_head('release/flocker-0.3.0pre1')
        self.repo.create_tag('0.3.0pre1')
        self.repo.create_head('release/flocker-0.3.0pre2')
        self.repo.create_tag('0.3.0pre2')
        self.assertEqual(
            self.calculate_base_branch(version='0.3.0pre3').name,
            "release/flocker-0.3.0pre2")

    def test_unparseable_tags(self):
        """
        There is no error raised if the repository contains a tag which cannot
        be parsed as a version.
        """
        self.repo.create_head('release/flocker-0.3.0unparseable')
        self.repo.create_tag('0.3.0unparseable')
        self.repo.create_head('release/flocker-0.3.0pre2')
        self.repo.create_tag('0.3.0pre2')
        self.assertEqual(
            self.calculate_base_branch(version='0.3.0pre3').name,
            "release/flocker-0.3.0pre2")

    def test_parent_repository_used(self):
        """
        If a path is given as the repository path, the parents of that file
        are searched until a Git repository is found.
        """
        self.assertEqual(
            calculate_base_branch(
                version='0.3.0dev1',
                path=FilePath(self.repo.working_dir).child('README').path,
            ).name,
            "master")

    def test_no_pre_releases_fails(self):
        """
        Trying to release a marketing release when no pre-release exists for it
        fails.
        """
        self.assertRaises(
            NoPreRelease,
            self.calculate_base_branch, '0.3.0')

    def test_missing_pre_release_fails(self):
        """
        Trying to release a pre-release when the previous pre-release does not
        exist fails.
        """
        self.repo.create_head('release/flocker-0.3.0pre1')
        self.repo.create_tag('0.3.0pre1')
        self.assertRaises(
            MissingPreRelease,
            self.calculate_base_branch, '0.3.0pre3')

    def test_base_branch_does_not_exist_fails(self):
        """
        Trying to create a release when the base branch does not exist fails.
        """
        self.repo.create_tag('0.3.0pre1')

        self.assertRaises(
            BaseBranchDoesNotExist,
            self.calculate_base_branch, '0.3.0')

    def test_tag_exists_fails(self):
        """
        Trying to create a release when a tag already exists for the given
        version fails.
        """
        self.repo.create_tag('0.3.0')
        self.assertRaises(
            TagExists,
            self.calculate_base_branch, '0.3.0')
