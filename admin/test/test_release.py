# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``admin.release``.
"""

import json
import os

from gzip import GzipFile
from StringIO import StringIO
import tempfile
from textwrap import dedent
from unittest import skipUnless

from effect import sync_perform, ComposedDispatcher, base_dispatcher
from git import GitCommandError, Repo

from requests.exceptions import HTTPError

from twisted.python.filepath import FilePath
from twisted.python.procutils import which
from twisted.python.usage import UsageError
from twisted.trial.unittest import SynchronousTestCase

from .. import release

from ..release import (
    upload_python_packages, upload_packages, update_repo,
    publish_docs, Environments,
    DocumentationRelease, DOCUMENTATION_CONFIGURATIONS, NotTagged, NotARelease,
    calculate_base_branch, create_release_branch,
    CreateReleaseBranchOptions, BranchExists, TagExists,
    MissingPreRelease, NoPreRelease,
    UploadOptions, create_pip_index, upload_pip_index,
    publish_homebrew_recipe, PushFailed,
    publish_vagrant_metadata, TestRedirectsOptions, get_expected_redirects,
)

from ..packaging import Distribution
from ..aws import FakeAWS, CreateCloudFrontInvalidation
from ..yum import FakeYum, yum_dispatcher
from hashlib import sha256

FLOCKER_PATH = FilePath(__file__).parent().parent().parent()


def hard_linking_possible():
    """
    Return True if hard linking is possible in the current directory, else
    return False.
    """
    scratch_directory = FilePath(tempfile.mkdtemp())
    file = scratch_directory.child('src')
    file.touch()
    try:
        os.link(file.path, scratch_directory.child('dst').path)
        return True
    except:
        return False
    finally:
        scratch_directory.remove()


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
                    '0.3.0+444.gf05215b/index.html': 'index-content',
                    '0.3.0+444.gf05215b/sub/index.html': 'sub-index-content',
                    '0.3.0+444.gf05215b/other.html': 'other-content',
                    '0.3.0+392.gd50b558/index.html': 'bad-index',
                    '0.3.0+392.gd50b558/sub/index.html': 'bad-sub-index',
                    '0.3.0+392.gd50b558/other.html': 'bad-other',
                },
            })
        self.publish_docs(aws, '0.3.0+444.gf05215b', '0.3.1',
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
                    '0.3.0+392.gd50b558/index.html': 'bad-index',
                    '0.3.0+392.gd50b558/sub/index.html': 'bad-sub-index',
                    '0.3.0+392.gd50b558/other.html': 'bad-other',
                }
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
                    '0.3.0+444.gf05215b/index.html': 'index-content',
                    '0.3.0+444.gf05215b/sub/index.html': 'sub-index-content',
                },
            })
        self.publish_docs(aws, '0.3.0+444.gf05215b', '0.3.1',
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
        self.publish_docs(aws, '0.3.0+444.gf05215b', '0.3.1',
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
                    'en/devel/': 'en/0.3.1.dev4/',
                },
            },
            s3_buckets={
                'clusterhq-staging-docs': {},
                'clusterhq-dev-docs': {},
            })
        self.publish_docs(aws, '0.3.0+444.gf01215b', '0.3.1.dev5',
                          environment=Environments.STAGING)
        self.assertEqual(
            aws.routing_rules, {
                'clusterhq-staging-docs': {
                    'en/latest/': 'en/0.3.0/',
                    'en/devel/': 'en/0.3.1.dev5/',
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
                    '0.3.0+444.gf05215b/index.html': '',
                    '0.3.0+444.gf05215b/sub/index.html': '',
                    '0.3.0+444.gf05215b/sub/other.html': '',
                },
            })
        self.publish_docs(aws, '0.3.0+444.gf05215b', '0.3.1',
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
                    '0.3.0+444.gf05215b/sub_index.html': '',
                },
            })
        self.publish_docs(aws, '0.3.0+444.gf05215b', '0.3.1',
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
        self.publish_docs(aws, '0.3.0+444.gf05215b', '0.3.1',
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
        self.publish_docs(aws, '0.3.0+444.gf05215b', '0.3.1',
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
                    'en/0.3.1.dev1/index.html': '',
                    'en/0.3.1.dev1/sub/index.html': '',
                },
                'clusterhq-dev-docs': {
                    '0.3.0+444.gf05215b/index.html': '',
                    '0.3.0+444.gf05215b/sub/index.html': '',
                    '0.3.0+444.gf05215b/sub/other.html': '',
                },
            })
        self.publish_docs(aws, '0.3.0+444.gf05215b', '0.3.1.dev1',
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
                        'en/0.3.1.dev1/',
                        'en/0.3.1.dev1/index.html',
                        'en/0.3.1.dev1/sub/',
                        'en/0.3.1.dev1/sub/index.html',
                        'en/0.3.1.dev1/sub/other.html',
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
                    'en/0.3.1.dev1/index.html': '',
                    'en/0.3.1.dev1/sub/index.html': '',
                },
                'clusterhq-dev-docs': {},
            })
        self.publish_docs(aws, '0.3.0+444.gf05215b', '0.3.1.dev1',
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
                        'en/0.3.1.dev1/',
                        'en/0.3.1.dev1/index.html',
                        'en/0.3.1.dev1/sub/',
                        'en/0.3.1.dev1/sub/index.html',
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
        self.publish_docs(aws, '0.3.0+444.gf05215b', '0.3.1.dev1',
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
                        'en/0.3.1.dev1/',
                        'en/0.3.1.dev1/index.html',
                        'en/0.3.1.dev1/sub/',
                        'en/0.3.1.dev1/sub/index.html',
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
            aws, '0.3.0+444.gf05215b', '0.3.1.dev1',
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
            aws, '0.3.1+444.gf05215b', '0.3.1.post1',
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
            aws, '0.3.1.post1', '0.3.1', environment=Environments.PRODUCTION)

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
            aws, '0.3.2rc1', '0.3.2rc1', environment=Environments.PRODUCTION)

    def test_publish_non_release_fails(self):
        """
        Trying to publish to version that isn't a release fails.
        """
        aws = FakeAWS(routing_rules={}, s3_buckets={})
        self.assertRaises(
            NotARelease,
            self.publish_docs,
            aws, '0.3.0+444.gf05215b', '0.3.0+444.gf05215b',
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
            doc_version='0.4.1.dev1',
            environment=Environments.STAGING,
            should_update=True
        )

    def test_error_key_dev_production(self):
        """
        Publishing documentation for a development release to the production
        bucket, does not update the error_key in any of the buckets.
        """
        self.assert_error_key_update(
            doc_version='0.4.1.dev1',
            environment=Environments.PRODUCTION,
            should_update=False
        )

    def test_error_key_pre_staging(self):
        """
        Publishing documentation for a pre-release to the staging
        bucket, updates the error_key in that bucket only.
        """
        self.assert_error_key_update(
            doc_version='0.4.1rc1',
            environment=Environments.STAGING,
            should_update=True
        )

    def test_error_key_pre_production(self):
        """
        Publishing documentation for a pre-release to the production
        bucket, does not update the error_key in any of the buckets.
        """
        self.assert_error_key_update(
            doc_version='0.4.1rc1',
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


class UpdateRepoTests(SynchronousTestCase):
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
                    packages, flocker_version, distribution):
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
                distribution=distribution,
            )
        )

    def test_fake_rpm(self):
        """
        Calling :func:`update_repo` downloads the new RPMs, creates the
        metadata, and uploads it to S3.

        - Existing packages on S3 are preserved in the metadata.
        - Other packages on the buildserver are not downloaded.
        - Existing metadata files are left untouched.
        """
        existing_s3_keys = {
            os.path.join(self.target_key, 'existing_package.rpm'): '',
            os.path.join(self.target_key,
                         'clusterhq-flocker-cli-0.3.3-0.dev.7.noarch.rpm'):
                'existing-content-to-be-replaced',  # noqa
            os.path.join(self.target_key, 'repodata', 'repomod.xml'):
                '<oldhash>-metadata.xml',
            os.path.join(self.target_key, 'repodata',
                         '<oldhash>-metadata.xml'):
                'metadata for: existing_package.rpm',
        }
        # Copy before passing to FakeAWS
        expected_keys = existing_s3_keys.copy()

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
            flocker_version='0.3.3.dev7',
            distribution=Distribution(name='centos', version='7'),
        )

        # The expected files are the new files plus the package which already
        # existed in S3.
        expected_packages = {
            'existing_package.rpm',
            'clusterhq-flocker-cli-0.3.3-0.dev.7.noarch.rpm',
            'clusterhq-flocker-node-0.3.3-0.dev.7.noarch.rpm',
        }

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

        - Existing packages on S3 are preserved in the metadata.
        - Other packages on the buildserver are not downloaded.
        """
        existing_s3_keys = {
            os.path.join(self.target_key, 'existing_package.deb'): '',
            os.path.join(self.target_key,
                         'clusterhq-flocker-cli_0.3.3-0.dev.7_all.deb'):
                'existing-content-to-be-replaced',  # noqa
            os.path.join(self.target_key, 'Packages.gz'):
                'metadata for: existing_package.deb',
        }
        # Copy before passing to FakeAWS
        expected_keys = existing_s3_keys.copy()

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
            flocker_version='0.3.3.dev7',
            distribution=Distribution(name='ubuntu', version='14.04'),
        )

        # The expected files are the new files plus the package which already
        # existed in S3.
        expected_packages = {
            'existing_package.deb',
            'clusterhq-flocker-cli_0.3.3-0.dev.7_all.deb',
            'clusterhq-flocker-node_0.3.3-0.dev.7_all.deb',
        }

        expected_keys.update({
            'test/target/key/Release': 'Origin: ClusterHQ\n',
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
                flocker_version='0.3.3.dev7',
                distribution=Distribution(name="centos", version="7"),
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

        FilePath(__file__).sibling('yum-repo').copyTo(source_repo)
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
            flocker_version='0.3.3.dev7',
            distribution=Distribution(name='centos', version='7'),
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

    @skipUnless(which('dpkg-scanpackages'),
                "Tests require the ``dpkg-scanpackages`` command.")
    def test_real_dpkg_utils(self):
        """
        Calling :func:`update_repo` with real dpkg utilities creates a
        repository in S3.

        The filenames in the repository metadata do not have the build
        directory in them.
        """
        source_repo = FilePath(self.mktemp())
        source_repo.createDirectory()

        FilePath(__file__).sibling('apt-repo').copyTo(source_repo)
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
            flocker_version='0.3.3.dev7',
            distribution=Distribution(name="ubuntu", version="14.04"),
        )

        expected_files = {
            os.path.join(self.target_key, file)
            for file in [
                'clusterhq-flocker-cli_0.3.3-0.dev.7_all.deb',
                'clusterhq-flocker-node_0.3.3-0.dev.7_all.deb',
                'Packages.gz',
                'Release',
            ]
        }
        files_on_s3 = aws.s3_buckets[self.target_bucket]

        # The original source repository contains no metadata.
        # This tests that CreateRepo creates the expected metadata files from
        # given RPMs, not that any metadata files are copied.
        self.assertEqual(expected_files, set(files_on_s3.keys()))

        # The repository is built in self.packages_directory
        # Ensure that that does not leak into the metadata.
        packages_gz = files_on_s3[os.path.join(self.target_key, 'Packages.gz')]
        with GzipFile(fileobj=StringIO(packages_gz), mode="r") as f:
            packages_metadata = f.read()
        self.assertNotIn(self.package_directory.path, packages_metadata)


class UploadPackagesTests(SynchronousTestCase):
    """
    Tests for :func:``upload_packages``.
    """
    def upload_packages(self, aws, yum,
                        scratch_directory, target_bucket, version,
                        build_server, top_level):
        """
        Call :func:``upload_packages``, interacting with a fake AWS and yum
        utilities.

        :param FakeAWS aws: Fake AWS to interact with.
        :param FakeYum yum: Fake yum utilities to interact with.

        See :py:func:`upload_packages` for other parameter documentation.
        """
        dispatchers = [aws.get_dispatcher(), yum.get_dispatcher(),
                       base_dispatcher]
        sync_perform(
            ComposedDispatcher(dispatchers),
            upload_packages(
                scratch_directory=scratch_directory,
                target_bucket=target_bucket,
                version=version,
                build_server=build_server,
                top_level=top_level,
            ),
        )

    def setUp(self):
        self.scratch_directory = FilePath(self.mktemp())
        self.scratch_directory.createDirectory()
        self.target_bucket = 'test-target-bucket'
        self.aws = FakeAWS(
            routing_rules={},
            s3_buckets={
                self.target_bucket: {},
            },
        )
        self.build_server = 'http://test-build-server.example'

    def test_repositories_created(self):
        """
        Calling :func:`upload_packages` creates repositories for supported
        distributions.
        """
        repo_contents = {
            'results/omnibus/0.3.3.dev1/centos-7/clusterhq-flocker-cli-0.3.3-0.dev.1.noarch.rpm': '',  # noqa
            'results/omnibus/0.3.3.dev1/centos-7/clusterhq-flocker-node-0.3.3-0.dev.1.noarch.rpm': '',  # noqa
            'results/omnibus/0.3.3.dev1/centos-7/clusterhq-python-flocker-0.3.3-0.dev.1.x86_64.rpm': '',  # noqa
            'results/omnibus/0.3.3.dev1/ubuntu-14.04/clusterhq-flocker-cli_0.3.3-0.dev.1_all.deb': '',  # noqa
            'results/omnibus/0.3.3.dev1/ubuntu-14.04/clusterhq-flocker-node_0.3.3-0.dev.1_all.deb': '',  # noqa
            'results/omnibus/0.3.3.dev1/ubuntu-14.04/clusterhq-python-flocker_0.3.3-0.dev.1_amd64.deb': '',  # noqa
            'results/omnibus/0.3.3.dev1/ubuntu-15.04/clusterhq-flocker-cli_0.3.3-0.dev.1_all.deb': '',  # noqa
            'results/omnibus/0.3.3.dev1/ubuntu-15.04/clusterhq-flocker-node_0.3.3-0.dev.1_all.deb': '',  # noqa
            'results/omnibus/0.3.3.dev1/ubuntu-15.04/clusterhq-python-flocker_0.3.3-0.dev.1_amd64.deb': '',  # noqa
        }

        self.upload_packages(
            aws=self.aws,
            yum=FakeYum(),
            scratch_directory=self.scratch_directory,
            target_bucket=self.target_bucket,
            version='0.3.3.dev1',
            build_server=create_fake_repository(self, files=repo_contents),
            top_level=FLOCKER_PATH,
        )

        expected_files = {
            'centos-testing/7/x86_64/clusterhq-flocker-cli-0.3.3-0.dev.1.noarch.rpm',  # noqa
            'centos-testing/7/x86_64/clusterhq-flocker-node-0.3.3-0.dev.1.noarch.rpm',  # noqa
            'centos-testing/7/x86_64/clusterhq-python-flocker-0.3.3-0.dev.1.x86_64.rpm',  # noqa
            'centos-testing/7/x86_64/repodata/repomod.xml',  # noqa
            'centos-testing/7/x86_64/repodata/<newhash>-metadata.xml',  # noqa
            'ubuntu-testing/14.04/amd64/clusterhq-flocker-cli_0.3.3-0.dev.1_all.deb',  # noqa
            'ubuntu-testing/14.04/amd64/clusterhq-flocker-node_0.3.3-0.dev.1_all.deb',  # noqa
            'ubuntu-testing/14.04/amd64/clusterhq-python-flocker_0.3.3-0.dev.1_amd64.deb',  # noqa
            'ubuntu-testing/14.04/amd64/Packages.gz',
            'ubuntu-testing/14.04/amd64/Release',
            'ubuntu-testing/15.04/amd64/clusterhq-flocker-cli_0.3.3-0.dev.1_all.deb',  # noqa
            'ubuntu-testing/15.04/amd64/clusterhq-flocker-node_0.3.3-0.dev.1_all.deb',  # noqa
            'ubuntu-testing/15.04/amd64/clusterhq-python-flocker_0.3.3-0.dev.1_amd64.deb',  # noqa
            'ubuntu-testing/15.04/amd64/Packages.gz',
            'ubuntu-testing/15.04/amd64/Release',
        }

        files_on_s3 = self.aws.s3_buckets[self.target_bucket].keys()
        self.assertEqual(expected_files, set(files_on_s3))

    def test_key_suffixes(self):
        """
        The OS part of the keys for created repositories have suffixes (or not)
        appropriate for the release type. In particular there is no "-testing"
        in keys created for a marketing release.
        """
        repo_contents = {
            'results/omnibus/0.3.3/centos-7/clusterhq-flocker-cli-0.3.3-1.noarch.rpm': '',  # noqa
            'results/omnibus/0.3.3/centos-7/clusterhq-flocker-node-0.3.3-1.noarch.rpm': '',  # noqa
            'results/omnibus/0.3.3/centos-7/clusterhq-python-flocker-0.3.3-1.x86_64.rpm': '',  # noqa
            'results/omnibus/0.3.3/ubuntu-14.04/clusterhq-flocker-cli_0.3.3-1_all.deb': '',  # noqa
            'results/omnibus/0.3.3/ubuntu-14.04/clusterhq-flocker-node_0.3.3-1_all.deb': '',  # noqa
            'results/omnibus/0.3.3/ubuntu-14.04/clusterhq-python-flocker_0.3.3-1_amd64.deb': '',  # noqa
            'results/omnibus/0.3.3/ubuntu-15.04/clusterhq-flocker-cli_0.3.3-1_all.deb': '',  # noqa
            'results/omnibus/0.3.3/ubuntu-15.04/clusterhq-flocker-node_0.3.3-1_all.deb': '',  # noqa
            'results/omnibus/0.3.3/ubuntu-15.04/clusterhq-python-flocker_0.3.3-1_amd64.deb': '',  # noqa
        }

        self.upload_packages(
            aws=self.aws,
            yum=FakeYum(),
            scratch_directory=self.scratch_directory,
            target_bucket=self.target_bucket,
            version='0.3.3',
            build_server=create_fake_repository(self, files=repo_contents),
            top_level=FLOCKER_PATH,
        )

        files_on_s3 = self.aws.s3_buckets[self.target_bucket].keys()
        self.assertEqual(set(), {f for f in files_on_s3 if '-testing' in f})

def create_fake_repository(test_case, files):
    """
    Create files in a directory to mimic a repository of packages.

    :param TestCase test_case: The test case to use for creating a temporary
        directory.
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


class UploadPythonPackagesTests(SynchronousTestCase):
    """
    Tests for :func:``upload_python_packages``.
    """

    def setUp(self):
        self.target_bucket = 'test-target-bucket'
        self.scratch_directory = FilePath(self.mktemp())
        self.top_level = FilePath(self.mktemp())
        self.top_level.makedirs()
        self.aws = FakeAWS(
            routing_rules={},
            s3_buckets={
                self.target_bucket: {},
            })

    def upload_python_packages(self):
        """
        Call :func:``upload_python_packages``, discarding output.

        :param bytes version: Version to upload packages for.
        See :py:func:`upload_python_packages` for other parameter
        documentation.
        """
        dispatchers = [self.aws.get_dispatcher(), base_dispatcher]

        with open(os.devnull, "w") as discard:
            sync_perform(
                ComposedDispatcher(dispatchers),
                upload_python_packages(
                    scratch_directory=self.scratch_directory,
                    target_bucket=self.target_bucket,
                    top_level=self.top_level,
                    output=discard,
                    error=discard,
                )
            )

    @skipUnless(hard_linking_possible(),
                "Hard linking is not possible in the current directory.")
    def test_distributions_uploaded(self):
        """
        Source and binary distributions of Flocker are uploaded to S3.
        """
        self.top_level.child('setup.py').setContent(
            dedent("""
                from setuptools import setup

                setup(
                    name="Flocker",
                    version="{package_version}",
                    py_modules=["Flocker"],
                )
                """).format(package_version='0.3.0')
        )

        self.upload_python_packages()

        aws_keys = self.aws.s3_buckets[self.target_bucket].keys()
        self.assertEqual(
            sorted(aws_keys),
            ['python/Flocker-0.3.0-py2-none-any.whl',
             'python/Flocker-0.3.0.tar.gz'])


class UploadOptionsTests(SynchronousTestCase):
    """
    Tests for :class:`UploadOptions`.
    """

    def test_must_be_release_version(self):
        """
        Trying to upload artifacts for a version which is not a release
        fails.
        """
        options = UploadOptions()
        self.assertRaises(
            NotARelease,
            options.parseOptions,
            ['--flocker-version', '0.3.0+444.gf05215b'])

    def test_documentation_release_fails(self):
        """
        Trying to upload artifacts for a documentation version fails.
        """
        options = UploadOptions()
        self.assertRaises(
            DocumentationRelease,
            options.parseOptions,
            ['--flocker-version', '0.3.0.post1'])


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


def create_git_repository(test_case, bare=False):
    """
    Create a git repository with a ``master`` branch and ``README``.

    :param test_case: The ``TestCase`` calling this.
    """
    directory = FilePath(test_case.mktemp())
    repository = Repo.init(path=directory.path, bare=bare)

    if not bare:
        directory.child('README').makedirs()
        directory.child('README').touch()
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
        branch = self.repo.create_head('release/flocker-0.3.0rc1')

        create_release_branch(version='0.3.0', base_branch=branch)
        self.assertEqual(
            self.repo.active_branch.name,
            "release/flocker-0.3.0")

    def test_branch_created_from_base(self):
        """
        The new branch is created from the given branch.
        """
        master = self.repo.active_branch
        branch = self.repo.create_head('release/flocker-0.3.0rc1')
        branch.checkout()
        FilePath(self.repo.working_dir).child('NEW_FILE').touch()
        self.repo.index.add(['NEW_FILE'])
        self.repo.index.commit('Add NEW_FILE')
        master.checkout()
        create_release_branch(version='0.3.0', base_branch=branch)
        self.assertIn((u'NEW_FILE', 0), self.repo.index.entries)


class CreatePipIndexTests(SynchronousTestCase):
    """
    Tests for :func:`create_pip_index`.
    """
    def setUp(self):
        self.scratch_directory = FilePath(self.mktemp())
        self.scratch_directory.makedirs()

    def test_index_created(self):
        """
        A pip index file is created for all wheel files.
        """
        index = create_pip_index(
            scratch_directory=self.scratch_directory,
            packages=[
                'Flocker-0.3.0-py2-none-any.whl',
                'Flocker-0.3.1-py2-none-any.whl'
            ]
        )

        expected = (
            '<html>\nThis is an index for pip\n<div>'
            '<a href="Flocker-0.3.0-py2-none-any.whl">'
            'Flocker-0.3.0-py2-none-any.whl</a><br />\n</div><div>'
            '<a href="Flocker-0.3.1-py2-none-any.whl">'
            'Flocker-0.3.1-py2-none-any.whl</a><br />\n</div></html>'
        )
        self.assertEqual(expected, index.getContent())

    def test_index_not_included(self):
        """
        The pip index file does not reference itself.
        """
        index = create_pip_index(
            scratch_directory=self.scratch_directory,
            packages=[
                'Flocker-0.3.0-py2-none-any.whl',
                'Flocker-0.3.1-py2-none-any.whl',
                'index.html',
            ]
        )

        expected = (
            '<html>\nThis is an index for pip\n<div>'
            '<a href="Flocker-0.3.0-py2-none-any.whl">'
            'Flocker-0.3.0-py2-none-any.whl</a><br />\n</div><div>'
            '<a href="Flocker-0.3.1-py2-none-any.whl">'
            'Flocker-0.3.1-py2-none-any.whl</a><br />\n</div></html>'
        )
        self.assertEqual(expected, index.getContent())

    def test_quoted_destination(self):
        """
        Destination links are quoted.
        """
        index = create_pip_index(
            scratch_directory=self.scratch_directory,
            packages=[
                '"Flocker-0.3.0-py2-none-any.whl',
            ]
        )

        expected = (
            '<html>\nThis is an index for pip\n<div>'
            '<a href="&quot;Flocker-0.3.0-py2-none-any.whl">'
            '"Flocker-0.3.0-py2-none-any.whl</a><br />\n</div></html>'
        )
        self.assertEqual(expected, index.getContent())

    def test_escaped_title(self):
        """
        Link titles are escaped.
        """
        index = create_pip_index(
            scratch_directory=self.scratch_directory,
            packages=[
                '>Flocker-0.3.0-py2-none-any.whl',
            ]
        )

        expected = (
            '<html>\nThis is an index for pip\n<div>'
            '<a href="&gt;Flocker-0.3.0-py2-none-any.whl">'
            '&gt;Flocker-0.3.0-py2-none-any.whl</a><br />\n</div></html>'
        )
        self.assertEqual(expected, index.getContent())


class UploadPipIndexTests(SynchronousTestCase):
    """
    Tests for :func:`upload_pip_index`.
    """
    def test_index_uploaded(self):
        """
        An index file is uploaded to S3.
        """
        bucket = 'clusterhq-archive'
        aws = FakeAWS(
            routing_rules={},
            s3_buckets={
                bucket: {
                    'python/Flocker-0.3.1-py2-none-any.whl': '',
                },
            })

        scratch_directory = FilePath(self.mktemp())
        scratch_directory.makedirs()

        sync_perform(
            ComposedDispatcher([aws.get_dispatcher(), base_dispatcher]),
            upload_pip_index(
                scratch_directory=scratch_directory,
                target_bucket=bucket))

        self.assertEqual(
            aws.s3_buckets[bucket]['python/index.html'],
            (
                '<html>\nThis is an index for pip\n<div>'
                '<a href="Flocker-0.3.1-py2-none-any.whl">'
                'Flocker-0.3.1-py2-none-any.whl</a><br />\n</div></html>'
            ))


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
            self.calculate_base_branch, '0.3.0+444.gf05215b')

    def test_weekly_release_base(self):
        """
        A weekly release is created from the "master" branch.
        """
        self.assertEqual(
            self.calculate_base_branch(version='0.3.0.dev1').name,
            "master")

    def test_doc_release_base(self):
        """
        A documentation release is created from the release which is having
        its documentation changed.
        """
        self.repo.create_head('release/flocker-0.3.0')
        self.assertEqual(
            self.calculate_base_branch(version='0.3.0.post1').name,
            "release/flocker-0.3.0")

    def test_first_pre_release(self):
        """
        The first pre-release for a marketing release is created from the
        "master" branch.
        """
        self.assertEqual(
            self.calculate_base_branch(version='0.3.0rc1').name,
            "master")

    def test_uses_previous_pre_release(self):
        """
        The second pre-release for a marketing release is created from the
        previous pre-release release branch.
        """
        self.repo.create_head('release/flocker-0.3.0rc1')
        self.repo.create_tag('0.3.0rc1')
        self.repo.create_head('release/flocker-0.3.0rc2')
        self.repo.create_tag('0.3.0rc2')
        self.assertEqual(
            self.calculate_base_branch(version='0.3.0rc3').name,
            "release/flocker-0.3.0rc2")

    def test_unparseable_tags(self):
        """
        There is no error raised if the repository contains a tag which cannot
        be parsed as a version.
        """
        self.repo.create_head('release/flocker-0.3.0unparseable')
        self.repo.create_tag('0.3.0unparseable')
        self.repo.create_head('release/flocker-0.3.0rc2')
        self.repo.create_tag('0.3.0rc2')
        self.assertEqual(
            self.calculate_base_branch(version='0.3.0rc3').name,
            "release/flocker-0.3.0rc2")

    def test_parent_repository_used(self):
        """
        If a path is given as the repository path, the parents of that file
        are searched until a Git repository is found.
        """
        self.assertEqual(
            calculate_base_branch(
                version='0.3.0.dev1',
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
        self.repo.create_head('release/flocker-0.3.0rc1')
        self.repo.create_tag('0.3.0rc1')
        self.assertRaises(
            MissingPreRelease,
            self.calculate_base_branch, '0.3.0rc3')

    def test_base_branch_does_not_exist_fails(self):
        """
        Trying to create a release when the base branch does not exist fails.
        """
        self.repo.create_tag('0.3.0rc1')

        self.assertRaises(
            GitCommandError,
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

    def test_branch_only_exists_remote(self):
        """
        If the test branch does not exist locally, but does exist as a remote
        branch a base branch can still be calculated.
        """
        self.repo.create_head('release/flocker-0.3.0rc1')
        self.repo.create_tag('0.3.0rc1')
        directory = FilePath(self.mktemp())
        clone = self.repo.clone(path=directory.path)

        self.assertEqual(
            calculate_base_branch(
                    version='0.3.0rc2',
                    path=clone.working_dir).name,
            "release/flocker-0.3.0rc1")


class PublishVagrantMetadataTests(SynchronousTestCase):
    """
    Tests for :func:`publish_vagrant_metadata`.
    """

    def setUp(self):
        self.target_bucket = 'clusterhq-archive'
        self.metadata_key = 'vagrant/flocker-tutorial.json'

    def metadata_version(self, version, box_filename, provider="virtualbox"):
        """
        Create a version section for Vagrant metadata, for a given box, with
        one provider: virtualbox.

        :param bytes version: The version of the box, normalised for Vagrant.
        :param bytes box_filename: The filename of the box.
        :param bytes provider: The provider for the box.

        :return: Dictionary to be used as a version section in Vagrant
            metadata.
        """
        return {
            "version": version,
            "providers": [
                {
                    "url": "https://example.com/" + box_filename,
                    "name": provider,
                }
            ],
        }

    def tutorial_metadata(self, versions):
        """
        Create example tutorial metadata.

        :param list versions: List of dictionaries of version sections.

        :return: Dictionary to be used as Vagrant metadata.
        """
        return {
            "description": "clusterhq/flocker-tutorial box.",
            "name": "clusterhq/flocker-tutorial",
            "versions": versions,
        }

    def publish_vagrant_metadata(self, aws, version):
        """
        Call :func:``publish_vagrant_metadata``, interacting with a fake AWS.

        :param FakeAWS aws: Fake AWS to interact with.
        :param version: See :py:func:`publish_vagrant_metadata`.
        """
        scratch_directory = FilePath(self.mktemp())
        scratch_directory.makedirs()
        box_url = "https://example.com/flocker-tutorial-{}.box".format(version)
        box_name = 'flocker-tutorial'
        sync_perform(
            ComposedDispatcher([aws.get_dispatcher(), base_dispatcher]),
            publish_vagrant_metadata(
                version=version,
                box_url=box_url,
                box_name=box_name,
                target_bucket=self.target_bucket,
                scratch_directory=scratch_directory))

    def test_no_metadata_exists(self):
        """
        A metadata file is added when one does not exist.
        """
        aws = FakeAWS(
            routing_rules={},
            s3_buckets={
                self.target_bucket: {},
            },
        )

        self.publish_vagrant_metadata(aws=aws, version='0.3.0')
        expected_version = self.metadata_version(
            version="0.3.0",
            box_filename="flocker-tutorial-0.3.0.box",
        )

        self.assertEqual(
            json.loads(aws.s3_buckets[self.target_bucket][self.metadata_key]),
            self.tutorial_metadata(versions=[expected_version]),
        )

    def test_metadata_content_type(self):
        """
        Vagrant requires a JSON metadata file to have a Content-Type of
        application/json.
        """
        aws = FakeAWS(
            routing_rules={},
            s3_buckets={
                self.target_bucket: {},
            },
        )

        self.publish_vagrant_metadata(aws=aws, version='0.3.0')

        self.assertEqual(
            aws.s3_buckets[self.target_bucket][self.metadata_key].content_type,
            'application/json'
        )

    def test_version_added(self):
        """
        A version is added to an existing metadata file.
        """
        existing_old_version = self.metadata_version(
            version="0.3.0",
            box_filename="flocker-tutorial-0.3.0.box",
        )

        existing_metadata = json.dumps(
            self.tutorial_metadata(versions=[existing_old_version])
        )

        aws = FakeAWS(
            routing_rules={},
            s3_buckets={
                self.target_bucket: {
                    'vagrant/flocker-tutorial.json': existing_metadata,
                },
            },
        )

        expected_new_version = self.metadata_version(
            version="0.4.0",
            box_filename="flocker-tutorial-0.4.0.box",
        )

        expected_metadata = self.tutorial_metadata(
            versions=[existing_old_version, expected_new_version])

        self.publish_vagrant_metadata(aws=aws, version='0.4.0')
        self.assertEqual(
            json.loads(aws.s3_buckets[self.target_bucket][self.metadata_key]),
            expected_metadata,
        )

    def test_version_normalised(self):
        """
        The version given is converted to a version number acceptable to
        Vagrant.
        """
        aws = FakeAWS(
            routing_rules={},
            s3_buckets={
                self.target_bucket: {},
            },
        )

        self.publish_vagrant_metadata(aws=aws, version='0.3.0_1')
        metadata = json.loads(
            aws.s3_buckets[self.target_bucket][self.metadata_key])
        # The underscore is converted to a period in the version.
        self.assertEqual(metadata['versions'][0]['version'], "0.3.0.1")

    def test_version_already_exists(self):
        """
        If a version already exists then its data is overwritten by the new
        metadata. This works even if the version is changed when being
        normalised.
        """
        existing_version = self.metadata_version(
            version="0.4.0.2314.g941011b",
            box_filename="old_filename",
            provider="old_provider",
        )

        existing_metadata = json.dumps(
            self.tutorial_metadata(versions=[existing_version])
        )

        aws = FakeAWS(
            routing_rules={},
            s3_buckets={
                self.target_bucket: {
                    'vagrant/flocker-tutorial.json': existing_metadata,
                },
            },
        )

        expected_version = self.metadata_version(
            version="0.4.0.2314.g941011b",
            box_filename="flocker-tutorial-0.4.0-2314-g941011b.box",
            provider="virtualbox",
        )

        self.publish_vagrant_metadata(aws=aws, version='0.4.0-2314-g941011b')

        metadata_versions = json.loads(
            aws.s3_buckets[self.target_bucket][self.metadata_key])['versions']

        self.assertEqual(metadata_versions, [expected_version])


class PublishHomebrewRecipeTests(SynchronousTestCase):
    """
    Tests for :func:`publish_homebrew_recipe`.
    """

    def setUp(self):
        self.source_repo = create_git_repository(test_case=self, bare=True)
        # Making a recipe involves interacting with PyPI, this should be
        # a parameter, not a patch. See:
        # https://clusterhq.atlassian.net/browse/FLOC-1759
        self.patch(release, 'make_recipe',
            lambda version, sdist_url:
                "Recipe for " + version + " at " + sdist_url)

    def test_commit_message(self):
        """
        The recipe is committed with a sensible message.
        """
        publish_homebrew_recipe(
            homebrew_repo_url=self.source_repo.git_dir,
            version='0.3.0',
            scratch_directory=FilePath(self.mktemp()),
            source_bucket="archive",
        )

        self.assertEqual(
            self.source_repo.head.commit.summary,
            u'Add recipe for Flocker version 0.3.0')

    def test_recipe_contents(self):
        """
        The passed in contents are in the recipe.
        """
        publish_homebrew_recipe(
            homebrew_repo_url=self.source_repo.git_dir,
            version='0.3.0',
            scratch_directory=FilePath(self.mktemp()),
            source_bucket="bucket-name",
        )

        recipe = self.source_repo.head.commit.tree['flocker-0.3.0.rb']
        self.assertEqual(recipe.data_stream.read(),
            'Recipe for 0.3.0 at https://bucket-name.s3.amazonaws.com/python/Flocker-0.3.0.tar.gz')  # noqa

    def test_push_fails(self):
        """
        If the push fails, an error is raised.
        """
        non_bare_repo = create_git_repository(test_case=self, bare=False)
        self.assertRaises(
            PushFailed,
            publish_homebrew_recipe,
            non_bare_repo.git_dir, '0.3.0', "archive", FilePath(self.mktemp()))

    def test_recipe_already_exists(self):
        """
        If a recipe already exists with the same name, it is overwritten.
        """
        publish_homebrew_recipe(
            homebrew_repo_url=self.source_repo.git_dir,
            version='0.3.0',
            scratch_directory=FilePath(self.mktemp()),
            source_bucket="archive",
        )

        self.patch(release, 'make_recipe',
            lambda version, sdist_url: "New content")

        publish_homebrew_recipe(
            homebrew_repo_url=self.source_repo.git_dir,
            version='0.3.0',
            scratch_directory=FilePath(self.mktemp()),
            source_bucket="archive",
        )

        recipe = self.source_repo.head.commit.tree['flocker-0.3.0.rb']
        self.assertEqual(recipe.data_stream.read(), 'New content')

class GetExpectedRedirectsTests(SynchronousTestCase):
    """
    Tests for :func:`get_expected_redirects`.
    """

    def test_marketing_release(self):
        """
        If a marketing release version is given, marketing release redirects
        are returned.
        """
        self.assertEqual(
            get_expected_redirects(flocker_version='0.3.0'),
            {
                '/': '/en/0.3.0/',
                '/en/': '/en/0.3.0/',
                '/en/latest': '/en/0.3.0/',
                '/en/latest/faq/index.html': '/en/0.3.0/faq/index.html',
            }
        )

    def test_development_release(self):
        """
        If a development release version is given, development release
        redirects are returned.
        """
        self.assertEqual(
            get_expected_redirects(flocker_version='0.3.0.dev1'),
            {
                '/en/devel': '/en/0.3.0.dev1/',
                '/en/devel/faq/index.html': '/en/0.3.0.dev1/faq/index.html',
            }
        )

    def test_documentation_release(self):
        """
        If a documentation release version is given, marketing release
        redirects are returned for the versions which is being updated.
        """
        self.assertEqual(
            get_expected_redirects(flocker_version='0.3.0.post1'),
            {
                '/': '/en/0.3.0/',
                '/en/': '/en/0.3.0/',
                '/en/latest': '/en/0.3.0/',
                '/en/latest/faq/index.html': '/en/0.3.0/faq/index.html',
            }
        )


class TestRedirectsOptionsTests(SynchronousTestCase):
    """
    Tests for :class:`TestRedirectsOptions`.
    """

    def test_default_environment(self):
        """
        The default environment is a staging environment.
        """
        options = TestRedirectsOptions()
        options.parseOptions([])
        self.assertEqual(options.environment, Environments.STAGING)

    def test_production_environment(self):
        """
        If "--production" is passed, a production environment is used.
        """
        options = TestRedirectsOptions()
        options.parseOptions(['--production'])
        self.assertEqual(options.environment, Environments.PRODUCTION)
