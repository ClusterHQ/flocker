# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``admin.release``.
"""

from unittest import TestCase
from characteristic import attributes, Attribute
from effect import (
    sync_perform, sync_performer,
    TypeDispatcher, ComposedDispatcher, base_dispatcher)

from ..release import (
    rpm_version, make_rpm_version,
    publish_docs,
    UpdateS3RoutingRule,
    ListS3Keys,
    DeleteS3Keys,
    CopyS3Keys,
    CreateCloudFrontInvalidation,
)


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


@attributes([
    Attribute('routing_rules'),
    Attribute('s3_buckets')
])
class FakeAWS(object):
    def __init__(self):
        self.cloudfront_invalidations = []

    @sync_performer
    def _perform_update_s3_routing_rule(self, dispatcher, intent):
        old_target = self.routing_rules[intent.bucket][intent.prefix]
        self.routing_rules[intent.bucket][intent.prefix] = intent.target_prefix
        return old_target

    @sync_performer
    def _perform_create_cloudfront_invalidation(self, dispathcer, intent):
        self.cloudfront_invalidations.append(intent)

    @sync_performer
    def _perform_delete_s3_keys(self, dispathcer, intent):
        bucket = self.s3_buckets[intent.bucket]
        for key in intent.keys:
            del bucket[intent.prefix + key]

    @sync_performer
    def _perform_copy_s3_keys(self, dispathcer, intent):
        source_bucket = self.s3_buckets[intent.source_bucket]
        destination_bucket = self.s3_buckets[intent.source_bucket]
        for key in intent.keys:
            destination_bucket[intent.destination_prefix + key] = (
                source_bucket[intent.source_prefix + key])

    @sync_performer
    def _perform_list_s3_keys(self, dispathcer, intent):
        bucket = self.s3_buckets[intent.bucket]
        return [key.name[len(intent.prefix):]
                for key in bucket
                if key.startswith(intent.prefix)]

    def get_dispatcher(self):
        return TypeDispatcher({
            UpdateS3RoutingRule: self._perform_update_s3_routing_rule,
            ListS3Keys: self._perform_list_s3_keys,
            DeleteS3Keys: self._perform_delete_s3_keys,
            CopyS3Keys: self._perform_copy_s3_keys,
            CreateCloudFrontInvalidation:
                self._perform_create_cloudfront_invalidation,
        })


class PublishDocsTests(TestCase):
    def test_stuff(self):
        aws = FakeAWS(
            routing_rules={
                'clusterhq-staging-docs': {
                    'en/latest/': 'en/0.3.2/',
                },
            },
            s3_buckets={
                'clusterhq-staging-docs': {},
                'clusterhq-dev-docs': {},
            })
        sync_perform(
            ComposedDispatcher([aws.get_dispatcher(), base_dispatcher]),
            publish_docs(
                '0.3.2+doc1', '0.3.2', 'clusterhq-staging-docs',
            ))
