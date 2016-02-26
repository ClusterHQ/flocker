# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for ``admin.release``.
"""

import os

from hashlib import sha256
from gzip import GzipFile
from random import randrange
from StringIO import StringIO
import tempfile
from textwrap import dedent
from unittest import skipUnless, skipIf, expectedFailure

from effect import sync_perform, ComposedDispatcher, base_dispatcher
from git import Repo

from hypothesis import given
from hypothesis.strategies import text, sampled_from

from requests.exceptions import HTTPError

from boto.s3.website import RoutingRules, RoutingRule

from twisted.python.filepath import FilePath
from twisted.python.procutils import which
from twisted.python.usage import UsageError

from pyrsistent import freeze, thaw, PClass, field

from .. import release

from ..release import (
    upload_python_packages, upload_packages, update_repo,
    parse_routing_rules, publish_docs, Environments,
    DocumentationRelease, DOCUMENTATION_CONFIGURATIONS, NotTagged, NotARelease,
    calculate_base_branch, create_release_branch,
    CreateReleaseBranchOptions, BranchExists, TagExists,
    UploadOptions, create_pip_index, upload_pip_index,
    publish_homebrew_recipe, PushFailed,
    update_license_file, UnexpectedDocumentationVersion
)

from ..packaging import Distribution
from ..aws import FakeAWS, CreateCloudFrontInvalidation, FakeAWSState, fake_aws
from ..yum import FakeYum, yum_dispatcher

from flocker.testtools import TestCase

from testtools.matchers import AfterPreprocessing, Equals

FLOCKER_PATH = FilePath(__file__).parent().parent().parent()


def hard_linking_possible():
    """
    Return True if hard linking is possible in the current directory, else
    return False.
    """
    scratch_directory = FilePath(tempfile.mkdtemp())
    test_file = scratch_directory.child('src')
    test_file.touch()
    try:
        os.link(test_file.path, scratch_directory.child('dst').path)
        return True
    except:
        return False
    finally:
        scratch_directory.remove()


def MatchesRoutingRules(rules):
    """
    Matches against routing rules.

    :param rules: The routing rules to match against.
    :type rules: ``list`` of ``RoutingRule``
    """
    return AfterPreprocessing(RoutingRules.to_xml,
                              Equals(RoutingRules(rules).to_xml()))


class ParseRoutingRulesTests(TestCase):
    """
    Tests for :func:``parse_routing_rules``.
    """

    def test_empty_config(self):
        """
        """
        rules = parse_routing_rules({}, "hostname")
        self.assertThat(rules, MatchesRoutingRules([]))

    @given(
        hostname=text(),
        replace=sampled_from(["replace_key", "replace_key_prefix"]),
    )
    def test_add_hostname(self, hostname, replace):
        """
        If a rule doesn't have a hostname
        - the passed hostname is added.
        - the replacement is prefixed with the common prefix.
        """
        rules = parse_routing_rules({
            "prefix/": {
                "key/": {replace: "replacement"},
            },
        }, hostname)
        self.assertThat(rules, MatchesRoutingRules([
            RoutingRule.when(key_prefix="prefix/key/").then_redirect(
                hostname=hostname,
                protocol="https",
                http_redirect_code=302,
                **{replace: "prefix/replacement"}
            ),
        ]))

    @given(
        hostname=text(),
        other_hostname=text(),
        replace=sampled_from(["replace_key", "replace_key_prefix"]),
    )
    def test_given_hostname(self, hostname, replace, other_hostname):
        """
        If a rule has a hostname, it is used unchanged and the common prefix is
        not included in the replacement.
        """
        rules = parse_routing_rules({
            "prefix/": {
                "key/": {replace: "replacement", "hostname": other_hostname},
            },
        }, hostname)
        self.assertThat(rules, MatchesRoutingRules([
            RoutingRule.when(key_prefix="prefix/key/").then_redirect(
                hostname=other_hostname,
                protocol="https",
                http_redirect_code=302,
                **{replace: "replacement"}
            ),
        ]))

    @given(
        hostname=text(),
    )
    def test_long_match_first(self, hostname):
        """
        When multiple redirects exist under a single prefix, the longest match
        is listed first.
        """
        rules = parse_routing_rules({
            "long/": {
                "est/first/": {"replace_key": "there"},
                "": {"replace_key": "here"},
            },
            "": {
                "long/est/": {"replace_key": "everywhere"},
            },
        }, hostname)
        self.assertThat(rules, MatchesRoutingRules([
            RoutingRule.when(key_prefix="long/est/first/").then_redirect(
                hostname=hostname,
                protocol="https",
                replace_key="long/there",
                http_redirect_code=302,
            ),
            RoutingRule.when(key_prefix="long/est/").then_redirect(
                hostname=hostname,
                protocol="https",
                replace_key="everywhere",
                http_redirect_code=302,
            ),
            RoutingRule.when(key_prefix="long/").then_redirect(
                hostname=hostname,
                protocol="https",
                replace_key="long/here",
                http_redirect_code=302,
            ),
        ]))


def random_version(weekly_release=False, commit_count=False):
    version = list(unicode(randrange(10)) for i in range(3))
    if weekly_release:
        version += [u'dev{}'.format(randrange(10))]
    if commit_count:
        version[-1] += u"+{}".format(randrange(1000))
        version += [u"g" + hex(randrange(10 ** 12))[2:]]

    return u'.'.join(version)


class DocBranch(PClass):
    name = field(type=unicode)
    version = field(type=unicode)

    @classmethod
    def from_version(cls, version):
        return cls(
            name=u"release/flocker-{}".format(version),
            version=version
        )

    @classmethod
    def from_branch(cls, name):
        return cls(
            name=name,
            version=random_version(weekly_release=True, commit_count=True)
        )


def example_keys(branches):
    keys = {
        u'index.html': u'',
        u'en/index.html': u'',
    }
    for branch in branches:
        prefix = branch.name
        keys.update({
            prefix + u'/index.html':
                u'index-content',
            prefix + u'/sub/index.html':
                u'sub-index-content',
            prefix + u'/other.html':
                u'other-content',
            prefix + u'/version.html':
                u'    <p>{}</p>    '.format(branch.version),
        })
    return freeze(keys)


def example_keys_for_versions(versions):
    return example_keys(
        branches=[DocBranch.from_version(v) for v in versions]
    )


STATE_EMPTY = FakeAWSState(
    s3_buckets={
        u"clusterhq-staging-docs": freeze({}),
        u"clusterhq-docs": freeze({}),
    }
)

WEEKLY_RELEASE_VERSION = u"1.10.3.dev2"

STATE_WEEKLY_PRE_PUBLICATION = STATE_EMPTY.transform(
    [u"s3_buckets", u"clusterhq-staging-docs"],
    freeze({
        u"release/flocker-{}/version.html".format(
            WEEKLY_RELEASE_VERSION
        ): WEEKLY_RELEASE_VERSION,
        u"release/flocker-{}/index.html".format(
            WEEKLY_RELEASE_VERSION
        ): u'index-content',
    })
)

STATE_WEEKLY_POST_PUBLICATION = STATE_WEEKLY_PRE_PUBLICATION.transform(
    [u"s3_buckets", u"clusterhq-docs"],
    freeze({
        u"en/{}/version.html".format(
            WEEKLY_RELEASE_VERSION
        ): WEEKLY_RELEASE_VERSION,
        u"en/{}/index.html".format(
            WEEKLY_RELEASE_VERSION
        ): u'index-content',
        u"en/devel/version.html": WEEKLY_RELEASE_VERSION,
        u"en/devel/index.html": u'index-content',
    })
).transform(
    [u"cloudfront_invalidations"],
    lambda l: l.append(
        CreateCloudFrontInvalidation(
            cname=u'docs.clusterhq.com',
            paths={u'en/devel/',
                   u'en/devel/index.html',
                   u'en/devel/version.html',
                   u'en/1.10.3.dev2/',
                   u'en/1.10.3.dev2/index.html',
                   u'en/1.10.3.dev2/version.html'}
        )
    )
).transform(
    [u"routing_rules", u"clusterhq-docs"],
    RoutingRules([])
)

MARKETING_RELEASE_VERSION = u"1.10.3"

STATE_MARKETING_PRE_PUBLICATION = STATE_WEEKLY_POST_PUBLICATION.transform(
    [u"s3_buckets", u"clusterhq-staging-docs"],
    lambda b: b.update({
        u"release/flocker-{}/version.html".format(
            MARKETING_RELEASE_VERSION
        ): MARKETING_RELEASE_VERSION
    })
).transform(
    [u"cloudfront_invalidations"],
    freeze([])
)

STATE_MARKETING_POST_PUBLICATION = STATE_MARKETING_PRE_PUBLICATION.transform(
    [u"s3_buckets", u"clusterhq-docs"],
    lambda b: b.update({
        u"en/{}/version.html".format(
            MARKETING_RELEASE_VERSION
        ): MARKETING_RELEASE_VERSION,
        u"en/latest/version.html": MARKETING_RELEASE_VERSION
    })
).transform(
    [u"cloudfront_invalidations"],
    lambda l: l.append(
        CreateCloudFrontInvalidation(
            cname=u'docs.clusterhq.com',
            paths={u'en/latest/',
                   u'en/latest/version.html',
                   u'en/1.10.3/',
                   u'en/1.10.3/version.html'}
        )
    )
).transform(
    [u"routing_rules", u"clusterhq-docs"],
    RoutingRules([])
).transform(
    [u"error_key", u"clusterhq-docs"],
    u'en/1.10.3/error_pages/404.html',
)

POST1_RELEASE_VERSION = u"1.10.3.post1"
STATE_POST1_PRE_PUBLICATION = STATE_MARKETING_POST_PUBLICATION.transform(
    [u"s3_buckets", u"clusterhq-staging-docs"],
    lambda b: b.update({
        u"release/flocker-{}/version.html".format(
            POST1_RELEASE_VERSION
        ): MARKETING_RELEASE_VERSION,
        u"release/flocker-{}/index.html".format(
            POST1_RELEASE_VERSION
        ): u"new-index-content"
    })
).transform(
    [u"cloudfront_invalidations"],
    freeze([])
)


STATE_POST1_POST_PUBLICATION = STATE_POST1_PRE_PUBLICATION.transform(
    [u"s3_buckets", u"clusterhq-docs"],
    lambda b: b.update({
        u"en/{}/index.html".format(
            MARKETING_RELEASE_VERSION
        ): u"new-index-content",
        u"en/latest/index.html": u"new-index-content",
    })
).transform(
    [u"cloudfront_invalidations"],
    lambda l: l.append(
        CreateCloudFrontInvalidation(
            cname=u'docs.clusterhq.com',
            paths={u'en/1.10.3/',
                   u'en/latest/',
                   u'en/latest/index.html',
                   u'en/latest/version.html',
                   u'en/1.10.3/version.html',
                   u'en/1.10.3/index.html'}
        )
    )
)


class PublishDocsTests(TestCase):
    """
    Tests for :func:``publish_docs``.
    """

    def publish_docs(self, aws,
                     flocker_version, doc_version, environment,
                     routing_config={}):
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
                         environment=environment,
                         routing_config=routing_config))

    def test_documentation_version_mismatch(self):
        """
        If the version number in the ``version.html`` file in the source
        directory does not match the destination version number,
        ``UnexpectedDocumentationVersion`` is raised with the mismatched
        version numbers.
        """
        unexpected_version = random_version()
        expected_version = WEEKLY_RELEASE_VERSION

        aws = FakeAWS(
            state=STATE_WEEKLY_PRE_PUBLICATION.transform(
                [u"s3_buckets", u"clusterhq-staging-docs",
                 u"release/flocker-{}/version.html".format(
                     WEEKLY_RELEASE_VERSION
                 )],
                unexpected_version
            )
        )
        exception = self.assertRaises(
            UnexpectedDocumentationVersion,
            self.publish_docs,
            aws=aws,
            flocker_version=expected_version,
            doc_version=expected_version,
            environment=Environments.STAGING
        )
        self.assertEqual(
            (unexpected_version, expected_version),
            (exception.documentation_version,
             exception.expected_version)
        )

    def test_copies_documentation_production_weekly(self):
        """
        Calling :func:`publish_docs` in production copies documentation from
        ``s3://clusterhq-staging-docs/release/flocker-<flocker_version>/`` to
        ``s3://clusterhq-docs/en/<doc_version>/`` and
        ``s3://clusterhq-docs/en/devel/`` for weekly releases.
        """
        aws = FakeAWS(state=STATE_WEEKLY_PRE_PUBLICATION)

        self.publish_docs(
            aws=aws,
            flocker_version=WEEKLY_RELEASE_VERSION,
            doc_version=WEEKLY_RELEASE_VERSION,
            environment=Environments.PRODUCTION
        )

        self.assertEqual(
            STATE_WEEKLY_POST_PUBLICATION,
            aws.state
        )

    def test_copies_documentation_production_marketing(self):
        """
        Calling :func:`publish_docs` in production copies documentation from
        ``s3://clusterhq-staging-docs/release/flocker-<flocker_version>/`` to
        ``s3://clusterhq-docs/en/<doc_version>/`` and
        ``s3://clusterhq-docs/en/latest/`` for marketing releases.
        """
        aws = FakeAWS(state=STATE_MARKETING_PRE_PUBLICATION)

        self.publish_docs(
            aws=aws,
            flocker_version=MARKETING_RELEASE_VERSION,
            doc_version=MARKETING_RELEASE_VERSION,
            environment=Environments.PRODUCTION
        )

        self.assertEqual(
            STATE_MARKETING_POST_PUBLICATION,
            aws.state
        )

    def test_overwrites_existing_documentation(self):
        """
        Calling :func:`publish_docs` replaces documentation from
        ``s3://clusterhq-staging-docs/en/<doc_version>/``.
        with documentation from
        ``s3://clusterhq-staging-docs/release/flocker-<flocker_version>/``.
        Files with changed content are updated.
        """
        initial_state = STATE_MARKETING_PRE_PUBLICATION.transform(
            [u's3_buckets', u'clusterhq-docs'],
            lambda b: b.update({
                u"en/{}/version.html".format(
                    MARKETING_RELEASE_VERSION
                ): random_version(),
                u"en/latest/version.html": random_version(),
            })
        )
        aws = FakeAWS(state=initial_state)

        self.publish_docs(
            aws=aws,
            flocker_version=MARKETING_RELEASE_VERSION,
            doc_version=MARKETING_RELEASE_VERSION,
            environment=Environments.PRODUCTION
        )

        self.assertEqual(
            STATE_MARKETING_POST_PUBLICATION,
            aws.state
        )

    @skipIf(
        True,
        "XXX This fails because ``publish_docs`` doesn't do a separate"
        "calculation of changed keys with the ``en/latest`` prefix."
    )
    def test_deletes_and_invalidates_documentation(self):
        """
        Calling :func:`publish_docs` deletes documentation pages from
        ``s3://clusterhq-staging-docs/en/<doc_version>/``.
        that do not exist in
        ``s3://clusterhq-staging-docs/release/flocker-<flocker_version>/``.

        """
        initial_state = STATE_MARKETING_PRE_PUBLICATION.transform(
            [u's3_buckets', u'clusterhq-docs'],
            lambda b: b.update({
                u"en/{}/unexpected_file.html".format(
                    MARKETING_RELEASE_VERSION
                ): "unexpected_content",
                u"en/latest/another/unexpected_file.html": "blah",
            })
        )
        aws = FakeAWS(state=initial_state)

        self.publish_docs(
            aws=aws,
            flocker_version=MARKETING_RELEASE_VERSION,
            doc_version=MARKETING_RELEASE_VERSION,
            environment=Environments.PRODUCTION
        )

        # Also invalidates the deleted keys.
        [original_invalidation] = getattr(
            STATE_MARKETING_POST_PUBLICATION,
            u"cloudfront_invalidations",
        )
        new_invalidation = CreateCloudFrontInvalidation(
            cname=original_invalidation.cname,
            paths=original_invalidation.paths.copy()
        )
        new_invalidation.paths.update({
            u'en/latest/another/unexpected_file.html',
            u'en/1.10.3/unexpected_file.html'
        })
        self.assertEqual(
            STATE_MARKETING_POST_PUBLICATION.transform(
                [u"cloudfront_invalidations"],
                freeze([new_invalidation])
            ),
            aws.state
        )

    def test_updated_routing_rules_production(self):
        """
        Calling :func:`publish_docs` updates the routing rules for the
        "clusterhq-docs" bucket.
        """
        initial_state = STATE_MARKETING_PRE_PUBLICATION
        aws = FakeAWS(state=initial_state)

        self.publish_docs(
            aws=aws,
            flocker_version=MARKETING_RELEASE_VERSION,
            doc_version=MARKETING_RELEASE_VERSION,
            environment=Environments.PRODUCTION,
            routing_config={
                u"prefix/": {
                    u"key/": {u"replace_key": u"replace"}
                },
            })
        self.assertThat(
            aws.state.routing_rules[u'clusterhq-docs'],
            MatchesRoutingRules([
                RoutingRule.when(key_prefix=u"prefix/key/").then_redirect(
                    replace_key=u"prefix/replace",
                    hostname=u"docs.clusterhq.com",
                    protocol=u"https",
                    http_redirect_code=u"302",
                ),
            ]))

    def test_production_gets_tagged_version(self):
        """
        Trying to publish to production, when the version being pushed isn't
        tagged raises an exception.
        """
        aws = FakeAWS(state=STATE_EMPTY)
        self.assertRaises(
            NotTagged,
            self.publish_docs,
            aws, '0.3.0+444.gf05215b', '0.3.1.dev1',
            environment=Environments.PRODUCTION)

    def test_production_can_publish_doc_version(self):
        """
        Publishing a documentation version to the version of the latest full
        release in production succeeds.
        """
        aws = FakeAWS(state=STATE_POST1_PRE_PUBLICATION)
        # Does not raise:
        self.publish_docs(
            aws=aws,
            flocker_version=POST1_RELEASE_VERSION,
            doc_version=MARKETING_RELEASE_VERSION,
            environment=Environments.PRODUCTION
        )
        self.expectThat(
            thaw(aws.state.s3_buckets),
            Equals(
                thaw(STATE_POST1_POST_PUBLICATION.s3_buckets)
            ),
        )
        self.expectThat(
            thaw(aws.state.routing_rules),
            Equals(
                thaw(STATE_POST1_POST_PUBLICATION.routing_rules)
            ),
        )
        self.expectThat(
            thaw(aws.state.error_key),
            Equals(
                thaw(STATE_POST1_POST_PUBLICATION.error_key)
            ),
        )
        self.expectThat(
            thaw(aws.state.cloudfront_invalidations),
            Equals(
                thaw(STATE_POST1_POST_PUBLICATION.cloudfront_invalidations)
            ),
        )

    @skipIf(
        True,
        "XXX: We don't do pre-releases any more. "
        "This test is redundant."
    )
    def test_production_can_publish_prerelease(self):
        """
        Publishing a pre-release succeeds.
        """
        aws = FakeAWS(state=STATE_EMPTY)
        # Does not raise:
        self.publish_docs(
            aws, '0.3.2rc1', '0.3.2rc1', environment=Environments.PRODUCTION)

    def test_publish_non_release_fails(self):
        """
        Trying to publish to version that isn't a release fails.
        """
        aws = FakeAWS(state=STATE_EMPTY)
        self.assertRaises(
            NotARelease,
            self.publish_docs,
            aws, '0.3.0+444.gf05215b', '0.3.0+444.gf05215b',
            environment=Environments.STAGING)


class UpdateRepoTests(TestCase):
    """
    Tests for :func:``update_repo``.
    """
    def setUp(self):
        super(UpdateRepoTests, self).setUp()
        self.target_bucket = u'test-target-bucket'
        self.target_key = u'test/target/key'
        self.package_directory = FilePath(self.mktemp())

        self.packages = [u'clusterhq-flocker-cli', u'clusterhq-flocker-node',
                         u'clusterhq-flocker-docker-plugin']

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
        existing_s3_keys = freeze({
            os.path.join(self.target_key, u'existing_package.rpm'): u'',
            os.path.join(self.target_key,
                         u'clusterhq-flocker-cli-0.3.3-0.dev.7.noarch.rpm'):
                u'existing-content-to-be-replaced',  # noqa
            os.path.join(self.target_key, u'repodata', u'repomod.xml'):
                u'<oldhash>-metadata.xml',
            os.path.join(self.target_key, u'repodata',
                         u'<oldhash>-metadata.xml'):
                u'metadata for: existing_package.rpm',
        })

        aws = FakeAWS(
            state=FakeAWSState(
                s3_buckets=freeze({
                    self.target_bucket: existing_s3_keys,
                }),
            )
        )

        unspecified_package = u'unspecified-package-0.3.3-0.dev.7.noarch.rpm'
        repo_contents = freeze({
            u'clusterhq-flocker-cli-0.3.3-0.dev.7.noarch.rpm': u'cli-package',
            u'clusterhq-flocker-node-0.3.3-0.dev.7.noarch.rpm':
                u'node-package',
            u'clusterhq-flocker-docker-plugin-0.3.3-0.dev.7.noarch.rpm':
                u'docker-plugin-package',
            unspecified_package: u'unspecified-package-content',
        })

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
        expected_packages = freeze({
            u'existing_package.rpm',
            u'clusterhq-flocker-cli-0.3.3-0.dev.7.noarch.rpm',
            u'clusterhq-flocker-node-0.3.3-0.dev.7.noarch.rpm',
            u'clusterhq-flocker-docker-plugin-0.3.3-0.dev.7.noarch.rpm',
        })

        expected_keys = existing_s3_keys.update({
            u'test/target/key/clusterhq-flocker-cli-0.3.3-0.dev.7.noarch.rpm':
                u'cli-package',
            u'test/target/key/clusterhq-flocker-node-0.3.3-0.dev.7.noarch.rpm':
                u'node-package',
            u'test/target/key/clusterhq-flocker-docker-plugin-0.3.3-0.dev.7.noarch.rpm':  # noqa
                u'docker-plugin-package',
        }).update({
            os.path.join(self.target_key, u'repodata', u'repomod.xml'):
                u'<newhash>-metadata.xml',
            os.path.join(self.target_key, u'repodata',
                         u'<newhash>-metadata.xml'):
                u'metadata content for: ' + ','.join(
                    sorted(expected_packages)
                ),
        })

        self.assertEqual(
            thaw(expected_keys),
            thaw(aws.state.s3_buckets[self.target_bucket])
        )

    def test_fake_deb(self):
        """
        Calling :func:`update_repo` downloads the new DEBs, creates the
        metadata, and uploads it to S3.

        - Existing packages on S3 are preserved in the metadata.
        - Other packages on the buildserver are not downloaded.
        """
        existing_s3_keys = freeze({
            os.path.join(self.target_key, u'existing_package.deb'): '',
            os.path.join(self.target_key,
                         u'clusterhq-flocker-cli_0.3.3-0.dev.7_all.deb'):
                u'existing-content-to-be-replaced',  # noqa
            os.path.join(self.target_key, u'Packages.gz'):
                u'metadata for: existing_package.deb',
        })

        aws = FakeAWS(
            state=FakeAWSState(
                s3_buckets=freeze({
                    self.target_bucket: existing_s3_keys,
                }),
            )
        )

        unspecified_package = u'unspecified-package_0.3.3-0.dev.7_all.deb'
        repo_contents = freeze({
            u'clusterhq-flocker-cli_0.3.3-0.dev.7_all.deb': u'cli-package',
            u'clusterhq-flocker-node_0.3.3-0.dev.7_all.deb': u'node-package',
            u'clusterhq-flocker-docker-plugin_0.3.3-0.dev.7_all.deb':
                u'docker-plugin-package',
            unspecified_package: u'unspecified-package-content',
        })

        self.update_repo(
            aws=aws,
            yum=FakeYum(),
            package_directory=self.package_directory,
            target_bucket=self.target_bucket,
            target_key=self.target_key,
            source_repo=create_fake_repository(self, files=repo_contents),
            packages=self.packages,
            flocker_version=u'0.3.3.dev7',
            distribution=Distribution(name=u'ubuntu', version=u'14.04'),
        )

        # The expected files are the new files plus the package which already
        # existed in S3.
        expected_packages = freeze({
            u'existing_package.deb',
            u'clusterhq-flocker-cli_0.3.3-0.dev.7_all.deb',
            u'clusterhq-flocker-node_0.3.3-0.dev.7_all.deb',
            u'clusterhq-flocker-docker-plugin_0.3.3-0.dev.7_all.deb',
        })

        expected_keys = existing_s3_keys.update({
            u'test/target/key/Release': u'Origin: ClusterHQ\n',
            u'test/target/key/clusterhq-flocker-cli_0.3.3-0.dev.7_all.deb':
                u'cli-package',
            u'test/target/key/clusterhq-flocker-node_0.3.3-0.dev.7_all.deb':
                u'node-package',
            u'test/target/key/clusterhq-flocker-docker-plugin_0.3.3-0.dev.7_all.deb':  # noqa
                u'docker-plugin-package',
            u'test/target/key/Packages.gz':
                u'Packages.gz for: ' + u','.join(sorted(expected_packages)),
            })

        self.assertEqual(
            expected_keys,
            aws.state.s3_buckets[self.target_bucket])

    def test_package_not_available_exception(self):
        """
        If a requested package is not available in the repository, a 404 error
        is raised.
        """
        aws = FakeAWS(
            state=FakeAWSState(
                s3_buckets=freeze({
                    self.target_bucket: freeze({}),
                }),
            )
        )

        exception = self.assertRaises(
            HTTPError,
            self.update_repo,
            aws=aws,
            yum=FakeYum(),
            package_directory=self.package_directory,
            target_bucket=self.target_bucket,
            target_key=self.target_key,
            source_repo=create_fake_repository(
                self, files={}),
            packages=self.packages,
            flocker_version=u'0.3.3.dev7',
            distribution=Distribution(name=u"centos", version=u"7"),
        )

        self.assertEqual(404, exception.response.status_code)

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
            state=FakeAWSState(
                s3_buckets={
                    self.target_bucket: freeze({}),
                },
            )
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
            flocker_version=u'0.3.3.dev7',
            distribution=Distribution(name=u'centos', version=u'7'),
        )

        expected_files = {
            os.path.join(self.target_key, file)
            for file in [
                u'clusterhq-flocker-cli-0.3.3-0.dev.7.noarch.rpm',
                u'clusterhq-flocker-node-0.3.3-0.dev.7.noarch.rpm',
                u'clusterhq-flocker-docker-plugin-0.3.3-0.dev.7.noarch.rpm',
                u'repodata/repomd.xml',
            ]
        }
        files_on_s3 = aws.state.s3_buckets[self.target_bucket]

        repodata_path = os.path.join(self.target_key, u'repodata')

        # Yum repositories prefix metadata files with the sha256 hash
        # of the file. Since these files contain timestamps, we calculate
        # the hash from the file, to determine the expected file names.
        for metadata_file in [
                u'other.sqlite.bz2',
                u'filelists.xml.gz',
                u'primary.xml.gz',
                u'filelists.sqlite.bz2',
                u'primary.sqlite.bz2',
                u'other.xml.gz',
                ]:
            for key in files_on_s3:
                if (key.endswith(metadata_file) and
                        key.startswith(repodata_path)):
                    expected_files.add(
                        os.path.join(
                            repodata_path,
                            sha256(files_on_s3[key]).hexdigest() +
                            u'-' + metadata_file)
                    )
                    break
            else:
                expected_files.add(
                    os.path.join(
                        repodata_path, u'<missing>-' + metadata_file))

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

        FilePath(__file__).sibling(u'apt-repo').copyTo(source_repo)
        repo_uri = u'file://' + source_repo.path

        aws = FakeAWS(
            state=FakeAWSState(
                s3_buckets=freeze({
                    self.target_bucket: freeze({}),
                }),
            )
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
            flocker_version=u'0.3.3.dev7',
            distribution=Distribution(name=u"ubuntu", version=u"14.04"),
        )

        expected_files = {
            os.path.join(self.target_key, file)
            for file in [
                u'clusterhq-flocker-cli_0.3.3-0.dev.7_all.deb',
                u'clusterhq-flocker-node_0.3.3-0.dev.7_all.deb',
                u'clusterhq-flocker-docker-plugin_0.3.3-0.dev.7_all.deb',
                u'Packages.gz',
                u'Release',
            ]
        }
        files_on_s3 = aws.state.s3_buckets[self.target_bucket]

        # The original source repository contains no metadata.
        # This tests that CreateRepo creates the expected metadata files from
        # given RPMs, not that any metadata files are copied.
        self.assertEqual(expected_files, set(files_on_s3.keys()))

        # The repository is built in self.packages_directory
        # Ensure that that does not leak into the metadata.
        packages_gz = files_on_s3[
            os.path.join(self.target_key, u'Packages.gz')
        ]
        with GzipFile(fileobj=StringIO(packages_gz), mode="r") as f:
            packages_metadata = f.read()
        self.assertNotIn(self.package_directory.path, packages_metadata)


class UploadPackagesTests(TestCase):
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
        super(UploadPackagesTests, self).setUp()
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

    # XXX: FLOC-3540 remove skip once the support for Ubuntu 15.10 is released
    @skipIf(True, "Skipping until the changes to support Ubuntu 15.10 "
            "are released - FLOC-3540")
    def test_repositories_created(self):
        """
        Calling :func:`upload_packages` creates repositories for supported
        distributions.
        """
        repo_contents = {
            'results/omnibus/0.3.3.dev1/centos-7/clusterhq-flocker-cli-0.3.3-0.dev.1.noarch.rpm': '',  # noqa
            'results/omnibus/0.3.3.dev1/centos-7/clusterhq-flocker-node-0.3.3-0.dev.1.noarch.rpm': '',  # noqa
            'results/omnibus/0.3.3.dev1/centos-7/clusterhq-flocker-docker-plugin-0.3.3-0.dev.1.noarch.rpm': '',  # noqa
            'results/omnibus/0.3.3.dev1/centos-7/clusterhq-python-flocker-0.3.3-0.dev.1.x86_64.rpm': '',  # noqa
            'results/omnibus/0.3.3.dev1/ubuntu-14.04/clusterhq-flocker-cli_0.3.3-0.dev.1_all.deb': '',  # noqa
            'results/omnibus/0.3.3.dev1/ubuntu-14.04/clusterhq-flocker-node_0.3.3-0.dev.1_all.deb': '',  # noqa
            'results/omnibus/0.3.3.dev1/ubuntu-14.04/clusterhq-flocker-docker-plugin_0.3.3-0.dev.1_all.deb': '',  # noqa
            'results/omnibus/0.3.3.dev1/ubuntu-14.04/clusterhq-python-flocker_0.3.3-0.dev.1_amd64.deb': '',  # noqa
            'results/omnibus/0.3.3.dev1/ubuntu-15.10/clusterhq-flocker-cli_0.3.3-0.dev.1_all.deb': '',  # noqa
            'results/omnibus/0.3.3.dev1/ubuntu-15.10/clusterhq-flocker-node_0.3.3-0.dev.1_all.deb': '',  # noqa
            'results/omnibus/0.3.3.dev1/ubuntu-15.10/clusterhq-flocker-docker-plugin_0.3.3-0.dev.1_all.deb': '',  # noqa
            'results/omnibus/0.3.3.dev1/ubuntu-15.10/clusterhq-python-flocker_0.3.3-0.dev.1_amd64.deb': '',  # noqa
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
            'centos-testing/7/x86_64/clusterhq-flocker-docker-plugin-0.3.3-0.dev.1.noarch.rpm',  # noqa
            'centos-testing/7/x86_64/clusterhq-python-flocker-0.3.3-0.dev.1.x86_64.rpm',  # noqa
            'centos-testing/7/x86_64/repodata/repomod.xml',  # noqa
            'centos-testing/7/x86_64/repodata/<newhash>-metadata.xml',  # noqa
            'ubuntu-testing/14.04/amd64/clusterhq-flocker-cli_0.3.3-0.dev.1_all.deb',  # noqa
            'ubuntu-testing/14.04/amd64/clusterhq-flocker-node_0.3.3-0.dev.1_all.deb',  # noqa
            'ubuntu-testing/14.04/amd64/clusterhq-flocker-docker-plugin_0.3.3-0.dev.1_all.deb',  # noqa
            'ubuntu-testing/14.04/amd64/clusterhq-python-flocker_0.3.3-0.dev.1_amd64.deb',  # noqa
            'ubuntu-testing/14.04/amd64/Packages.gz',
            'ubuntu-testing/14.04/amd64/Release',
            'ubuntu-testing/15.10/amd64/clusterhq-flocker-cli_0.3.3-0.dev.1_all.deb',  # noqa
            'ubuntu-testing/15.10/amd64/clusterhq-flocker-node_0.3.3-0.dev.1_all.deb',  # noqa
            'ubuntu-testing/15.10/amd64/clusterhq-flocker-docker-plugin_0.3.3-0.dev.1_all.deb',  # noqa
            'ubuntu-testing/15.10/amd64/clusterhq-python-flocker_0.3.3-0.dev.1_amd64.deb',  # noqa
            'ubuntu-testing/15.10/amd64/Packages.gz',
            'ubuntu-testing/15.10/amd64/Release',
            'ubuntu-testing/15.10/amd64/Release',
        }

        files_on_s3 = self.aws.s3_buckets[self.target_bucket].keys()
        self.assertEqual(expected_files, set(files_on_s3))

    # XXX: FLOC-3540 remove skip once the support for Ubuntu 15.10 is released
    @skipIf(True, "Skipping until the changes to support Ubuntu 15.10"
            " are released - FLOC-3540")
    def test_key_suffixes(self):
        """
        The OS part of the keys for created repositories have suffixes (or not)
        appropriate for the release type. In particular there is no "-testing"
        in keys created for a marketing release.
        """
        repo_contents = {
            'results/omnibus/0.3.3/centos-7/clusterhq-flocker-cli-0.3.3-1.noarch.rpm': '',  # noqa
            'results/omnibus/0.3.3/centos-7/clusterhq-flocker-node-0.3.3-1.noarch.rpm': '',  # noqa
            'results/omnibus/0.3.3/centos-7/clusterhq-flocker-docker-plugin-0.3.3-1.noarch.rpm': '',  # noqa
            'results/omnibus/0.3.3/centos-7/clusterhq-python-flocker-0.3.3-1.x86_64.rpm': '',  # noqa
            'results/omnibus/0.3.3/ubuntu-14.04/clusterhq-flocker-cli_0.3.3-1_all.deb': '',  # noqa
            'results/omnibus/0.3.3/ubuntu-14.04/clusterhq-flocker-node_0.3.3-1_all.deb': '',  # noqa
            'results/omnibus/0.3.3/ubuntu-14.04/clusterhq-flocker-docker-plugin_0.3.3-1_all.deb': '',  # noqa
            'results/omnibus/0.3.3/ubuntu-14.04/clusterhq-python-flocker_0.3.3-1_amd64.deb': '',  # noqa
            'results/omnibus/0.3.3/ubuntu-15.10/clusterhq-flocker-cli_0.3.3-1_all.deb': '',  # noqa
            'results/omnibus/0.3.3/ubuntu-15.10/clusterhq-flocker-node_0.3.3-1_all.deb': '',  # noqa
            'results/omnibus/0.3.3/ubuntu-15.10/clusterhq-flocker-docker-plugin_0.3.3-1_all.deb': '',  # noqa
            'results/omnibus/0.3.3/ubuntu-15.10/clusterhq-python-flocker_0.3.3-1_amd64.deb': '',  # noqa
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


class UploadPythonPackagesTests(TestCase):
    """
    Tests for :func:``upload_python_packages``.
    """

    def setUp(self):
        super(UploadPythonPackagesTests, self).setUp()
        self.target_bucket = u'test-target-bucket'
        self.scratch_directory = FilePath(self.mktemp())
        self.top_level = FilePath(self.mktemp())
        self.top_level.makedirs()
        self.aws = FakeAWS(
            state=FakeAWSState(
                routing_rules=freeze({}),
                s3_buckets=freeze({
                    self.target_bucket: {},
                })
            )
        )

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

        aws_keys = self.aws.state.s3_buckets[self.target_bucket].keys()
        self.assertEqual(
            sorted(aws_keys),
            ['python/Flocker-0.3.0-py2-none-any.whl',
             'python/Flocker-0.3.0.tar.gz'])


class UploadOptionsTests(TestCase):
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


class CreateReleaseBranchOptionsTests(TestCase):
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


class CreateReleaseBranchTests(TestCase):
    """
    Tests for :func:`create_release_branch`.
    """
    def setUp(self):
        super(CreateReleaseBranchTests, self).setUp()
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


class CreatePipIndexTests(TestCase):
    """
    Tests for :func:`create_pip_index`.
    """
    def setUp(self):
        super(CreatePipIndexTests, self).setUp()
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


class UploadPipIndexTests(TestCase):
    """
    Tests for :func:`upload_pip_index`.
    """
    def test_index_uploaded(self):
        """
        An index file is uploaded to S3.
        """
        bucket = u'clusterhq-archive'
        aws = FakeAWS(
            state=FakeAWSState(
                s3_buckets=freeze({
                    bucket: {
                        u'python/Flocker-0.3.1-py2-none-any.whl': u'',
                    },
                })
            )
        )

        scratch_directory = FilePath(self.mktemp())
        scratch_directory.makedirs()

        sync_perform(
            ComposedDispatcher([aws.get_dispatcher(), base_dispatcher]),
            upload_pip_index(
                scratch_directory=scratch_directory,
                target_bucket=bucket))

        self.assertEqual(
            aws.state.s3_buckets[bucket][u'python/index.html'],
            (
                u'<html>\nThis is an index for pip\n<div>'
                u'<a href="Flocker-0.3.1-py2-none-any.whl">'
                u'Flocker-0.3.1-py2-none-any.whl</a><br />\n</div></html>'
            ))


class CalculateBaseBranchTests(TestCase):
    """
    Tests for :func:`calculate_base_branch`.
    """

    def setUp(self):
        super(CalculateBaseBranchTests, self).setUp()
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

    def test_first_pre_release(self):
        """
        The first pre-release for a marketing release is created from the
        "master" branch.
        """
        self.assertEqual(
            self.calculate_base_branch(version='0.3.0rc1').name,
            "master")

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
            "master")

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
            "master")


class PublishHomebrewRecipeTests(TestCase):
    """
    Tests for :func:`publish_homebrew_recipe`.
    """

    def setUp(self):
        super(PublishHomebrewRecipeTests, self).setUp()
        self.source_repo = create_git_repository(test_case=self, bare=True)
        # Making a recipe involves interacting with PyPI, this should be
        # a parameter, not a patch. See:
        # https://clusterhq.atlassian.net/browse/FLOC-1759
        self.patch(
            release, 'make_recipe',
            lambda version, sdist_url, requirements_path:
            "Recipe for " + version + " at " + sdist_url
        )

    def test_commit_message(self):
        """
        The recipe is committed with a sensible message.
        """
        publish_homebrew_recipe(
            homebrew_repo_url=self.source_repo.git_dir,
            version='0.3.0',
            scratch_directory=FilePath(self.mktemp()),
            source_bucket="archive",
            top_level=FLOCKER_PATH,
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
            top_level=FLOCKER_PATH,
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
            non_bare_repo.git_dir,
            '0.3.0',
            "archive",
            FilePath(self.mktemp()),
            top_level=FLOCKER_PATH,
        )

    def test_recipe_already_exists(self):
        """
        If a recipe already exists with the same name, it is overwritten.
        """
        publish_homebrew_recipe(
            homebrew_repo_url=self.source_repo.git_dir,
            version='0.3.0',
            scratch_directory=FilePath(self.mktemp()),
            source_bucket="archive",
            top_level=FLOCKER_PATH,
        )

        self.patch(release, 'make_recipe',
                   lambda version, sdist_url, requirements_path: "New content")

        publish_homebrew_recipe(
            homebrew_repo_url=self.source_repo.git_dir,
            version='0.3.0',
            scratch_directory=FilePath(self.mktemp()),
            source_bucket="archive",
            top_level=FLOCKER_PATH,
        )

        recipe = self.source_repo.head.commit.tree['flocker-0.3.0.rb']
        self.assertEqual(recipe.data_stream.read(), 'New content')


class UpdateLicenseFileTests(TestCase):
    """
    Tests for :func:`update_license_file`.
    """

    def test_update_license_file(self):
        """
        A LICENSE file is written to the top level directory from a template in
        the admin directory, and is formatted to include the given year.
        """
        top_level = FilePath(self.mktemp())
        top_level.child('admin').makedirs()
        top_level.child('admin').child('LICENSE.template').setContent(
            "Text including the current year: {current_year}.")
        update_license_file(args=[], top_level=top_level, year=123)

        self.assertEqual(
            top_level.child('LICENSE').getContent(),
            "Text including the current year: 123."
        )
