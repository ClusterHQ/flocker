# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``admin.release``.
"""

from unittest import TestCase
from effect import sync_perform, ComposedDispatcher, base_dispatcher

from ..release import (
    rpm_version, make_rpm_version,
    publish_docs,
)
from ..aws import FakeAWS, CreateCloudFrontInvalidation


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
                    expected_rpm_version
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
            unicode(exception.exception)
        )


class PublishDocsTests(TestCase):

    def publish_docs(self, aws,
                     flocker_version, doc_version, production=False):
        """
        Call ``publish_docs``, interacting with a fake AWS.

        :param FakeAWS aws: Fake AWS to interact with.
        :param flocker_version: See :py:func:`flocker_version`.
        :param doc_version: See :py:func:`doc_version`.
        :param production: See :py:func:`production`.
        """
        sync_perform(
            ComposedDispatcher([aws.get_dispatcher(), base_dispatcher]),
            publish_docs(flocker_version, doc_version, production=production))

    def test_copies_documentation(self):
        """
        Calling :func:`publish_docs` copies documentation from
        ``s3://clusterhq-dev-docs/<flocker_version/`` to
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
        self.publish_docs(aws, '0.3.0-444-gf05215b', '0.3.1', production=False)
        self.assertEqual(
            aws.s3_buckets['clusterhq-staging-docs'], {
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
        with documentation from ``s3://clusterhq-dev-docs/<flocker_version/``.
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
        self.publish_docs(aws, '0.3.0-444-gf05215b', '0.3.1', production=False)
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
        Calling :func:`publish_docs` updates the redirect for ``en/latest/*``
        to point at ``en/<doc_version>/*``. Any other redirects are left
        untouched.
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
        self.publish_docs(aws, '0.3.0-444-gf05215b', '0.3.1', production=False)
        self.assertEqual(
            aws.routing_rules, {
                'clusterhq-staging-docs': {
                    # CHECKME: Does there need to be a leading `/`?
                    'en/latest/': 'en/0.3.1/',
                    'en/devel/': 'en/0.3.1.dev4/',
                },
            })

    def test_creates_cloudfront_invalidation(self):
        """
        Calling :func:`publish_docs` creates an invalidation for
        - en/latest/
        - en/<doc_version>/
        each for every path
        - in the new documentation for <doc_version>
        - in the old documentation for <doc_version>
        - in the version that was previously en/latest/
        and for each '`index.html`' the path without ``index.html``.
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
                    'en/0.3.1/missing.html': '',
                    'en/0.3.0/index.html': '',
                    'en/0.3.0/sub/index.html': '',
                    'en/0.3.0/old-version.html': '',
                },
                'clusterhq-dev-docs': {
                    '0.3.0-444-gf05215b/index.html': '',
                    '0.3.0-444-gf05215b/sub/index.html': '',
                    '0.3.0-444-gf05215b/sub/other.html': '',
                },
            })
        self.publish_docs(aws, '0.3.0-444-gf05215b', '0.3.1', production=False)
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
                        'en/latest/missing.html',
                        'en/latest/old-version.html',
                        'en/0.3.1/',
                        'en/0.3.1/index.html',
                        'en/0.3.1/sub/',
                        'en/0.3.1/sub/index.html',
                        'en/0.3.1/sub/other.html',
                        'en/0.3.1/missing.html',
                        'en/0.3.1/old-version.html',
                    }),
            ])
