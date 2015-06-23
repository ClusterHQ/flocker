# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for :module:`flocker.docs.version`.
"""


from twisted.trial.unittest import SynchronousTestCase

from packaging.version import Version as PEP440Version

from pyrsistent import PRecord, field

from ..version import (
    _parse_version, FlockerVersion,
    get_doc_version, get_installable_version, get_pre_release,
    get_package_key_suffix,
    is_pre_release, is_release, is_weekly_release,
    target_release,
    NotAPreRelease, UnparseableVersion,

)

from flocker.common.version import RPMVersion, make_rpm_version


class MakeRpmVersionTests(SynchronousTestCase):
    """
    Tests for ``make_rpm_version``.
    """
    def test_good(self):
        """
        ``make_rpm_version`` gives the expected ``RPMVersion`` instances when
        supplied with valid ``flocker_version_number``s.
        """
        expected = {
            '0.1.0': RPMVersion(version='0.1.0', release='1'),
            '0.1.0+99.g3d644b1': RPMVersion(
                version='0.1.0', release='1.99.g3d644b1'),
            '0.1.1pre1': RPMVersion(version='0.1.1', release='0.pre.1'),
            '0.1.1': RPMVersion(version='0.1.1', release='1'),
            '0.2.0dev1': RPMVersion(version='0.2.0', release='0.dev.1'),
            '0.2.0dev2+99.g3d644b1':
                RPMVersion(version='0.2.0', release='0.dev.2.99.g3d644b1'),
            '0.2.0dev3+100.g3d644b2.dirty': RPMVersion(
                version='0.2.0', release='0.dev.3.100.g3d644b2.dirty'),
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
        ``make_rpm_version`` raises ``UnparseableVersion`` when supplied with a
        version with a non-integer pre or dev suffix number.
        """
        with self.assertRaises(UnparseableVersion):
            make_rpm_version('0.1.2preX')


class InvalidVersionTests(SynchronousTestCase):
    """
    Tests for invalid versions.
    """

    def test_invalid_Version(self):
        """
        If an invalid vesion is passed to ``_parse_version``,
        ``UnparseableVersion`` is raised.
        """
        self.assertRaises(UnparseableVersion, _parse_version, 'unparseable')


class VersionCase(PRecord):
    """
    Description of a version and its expected interpretations.

    :param bytes version: The version to parse.

    :param FlockerVersion flocker_version: The parsed version.
    :param bytes doc_version: The corresponding doc version.
    :param bytes installable_version: The corresponding installable version.
    :param bool is_release: Whether the version corresponds to a
        release.
    :param bool is_weekly_release: Whether the version corresponds
        to a weekly release.
    :param bool is_pre_release: Whether the version corresponds to
        a pre-release.
    """
    version = field(bytes, mandatory=True)
    flocker_version = field(FlockerVersion, mandatory=True)
    doc_version = field(bytes, mandatory=True)
    installable_version = field(bytes, mandatory=True)
    is_release = field(bool, mandatory=True)
    is_weekly_release = field(bool, mandatory=True)
    is_pre_release = field(bool, mandatory=True)


def build_version_test(name, version_case):
    """
    Create a test case that checks that a given version
    is interpreted as expected.
    """
    class Tests(SynchronousTestCase):
        def test_flocker_version(self):
            self.assertEqual(
                _parse_version(version_case.version),
                version_case.flocker_version,
                "Version doesn't match expected parsed version.",
            )

        def test_doc_version(self):
            self.assertEqual(
                get_doc_version(version_case.version),
                version_case.doc_version,
                "Calculated doc version doesn't match expected doc version.",
            )

        def test_installable_version(self):
            self.assertEqual(
                get_installable_version(version_case.version),
                version_case.installable_version,
                "Calculated installable version doesn't match"
                "expected installable version.",)

        def test_is_release(self):
            self.assertEqual(
                is_release(version_case.version),
                version_case.is_release,
            )

        def test_is_weekly_release(self):
            self.assertEqual(
                is_weekly_release(version_case.version),
                version_case.is_weekly_release,
            )

        def test_is_pre_release(self):
            self.assertEqual(
                is_pre_release(version_case.version),
                version_case.is_pre_release,
            )

        def test_pep_440(self):
            PEP440Version(version_case.version)

    Tests.__name__ = name
    return Tests


MarkettingVersionTests = build_version_test(
    "MarkettingVersionTests",
    VersionCase(
        version=b'0.3.2',
        flocker_version=FlockerVersion(
            major=b'0',
            minor=b'3',
            micro=b'2',
        ),
        doc_version=b'0.3.2',
        installable_version=b'0.3.2',
        is_release=True,
        is_weekly_release=False,
        is_pre_release=False,
    ),
)
WeeklyReleaseTests = build_version_test(
    "WeeklyReleaseTests",
    VersionCase(
        version=b'0.3.2dev1',
        flocker_version=FlockerVersion(
            major=b'0',
            minor=b'3',
            micro=b'2',
            weekly_release=b'1',
        ),
        doc_version=b'0.3.2dev1',
        installable_version=b'0.3.2dev1',
        is_release=False,
        is_weekly_release=True,
        is_pre_release=False,
    ),
)
PreReleaseTests = build_version_test(
    "PreReleaseTests",
    VersionCase(
        version=b'0.3.2pre1',
        flocker_version=FlockerVersion(
            major=b'0',
            minor=b'3',
            micro=b'2',
            pre_release=b'1',
        ),
        doc_version=b'0.3.2pre1',
        installable_version=b'0.3.2pre1',
        is_release=False,
        is_weekly_release=False,
        is_pre_release=True,
    ),
)
DevelopmentVersionTests = build_version_test(
    "DevelopmentVersionTestss",
    VersionCase(
        version=b'0.3.2+1.gf661a6a',
        flocker_version=FlockerVersion(
            major=b'0',
            minor=b'3',
            micro=b'2',
            commit_count=b'1',
            commit_hash=b'f661a6a',
        ),
        doc_version=b'0.3.2+1.gf661a6a',
        installable_version=b'0.3.2',
        is_release=False,
        is_weekly_release=False,
        is_pre_release=False,
    ),
)
DirtyVersionTests = build_version_test(
    "DirtyVersionTests",
    VersionCase(
        version=b'0.3.2+1.gf661a6a.dirty',
        flocker_version=FlockerVersion(
            major=b'0',
            minor=b'3',
            micro=b'2',
            commit_count=b'1',
            commit_hash=b'f661a6a',
            dirty=b'.dirty',
        ),
        doc_version=b'0.3.2+1.gf661a6a.dirty',
        installable_version=b'0.3.2',
        is_release=False,
        is_weekly_release=False,
        is_pre_release=False,
    ),
)
DocReleaseTests = build_version_test(
    "DocReleaseTests",
    VersionCase(
        version=b'0.3.2.post11',
        flocker_version=FlockerVersion(
            major=b'0',
            minor=b'3',
            micro=b'2',
            documentation_revision=b'11',
        ),
        doc_version=b'0.3.2',
        installable_version=b'0.3.2',
        is_release=True,
        is_weekly_release=False,
        is_pre_release=False,
    ),
)
DocReleaseDirtyTests = build_version_test(
    "DocReleaseDirtyTests",
    VersionCase(
        version=b'0.3.2.post11+1.gf661a6a.dirty',
        flocker_version=FlockerVersion(
            major=b'0',
            minor=b'3',
            micro=b'2',
            documentation_revision=b'11',
            commit_count=b'1',
            commit_hash=b'f661a6a',
            dirty=b'.dirty',
        ),
        doc_version=b'0.3.2.post11+1.gf661a6a.dirty',
        installable_version=b'0.3.2',
        is_release=False,
        is_weekly_release=False,
        is_pre_release=False,
    ),
)


class GetPreReleaseTests(SynchronousTestCase):
    """
    Tests for :function:`get_pre_release`.
    """

    def test_not_pre_release(self):
        """
        If a version which is not a pre-release is passed to
        ``get_pre_release``, ``NotAPreRelease`` is raised.
        """
        self.assertRaises(NotAPreRelease, get_pre_release, '0.3.0')

    def test_pre_release(self):
        """
        When a pre-release is passed to ``get_pre_release``, the number of the
        pre-release is returned.
        """
        self.assertEqual(get_pre_release('0.3.2pre3'), 3)


class TargetReleaseTests(SynchronousTestCase):
    """
    Tests for :function:`target_release`.
    """

    def test_not_pre_release(self):
        """
        If a version which is not a pre-release is passed to
        ``target_release``, ``NotAPreRelease`` is raised.
        """
        self.assertRaises(NotAPreRelease, target_release, '0.3.0')

    def test_pre_release(self):
        """
        When a pre-release is passed to ``target_release``, target final
        release is returned.
        """
        self.assertEqual(target_release('0.3.2pre3'), '0.3.2')


class GetPackageKeySuffixTests(SynchronousTestCase):
    """
    Tests for :function:`get_package_key_suffix`.
    """

    def test_marketing_release(self):
        """
        If a marketing release is passed to ``get_package_key_suffix``, an
        empty string is returned.
        """
        self.assertEqual(get_package_key_suffix('0.3.0'), "")

    def test_documentation_release(self):
        """
        If a documentation release is passed to ``get_package_key_suffix``, an
        empty string is returned.
        """
        self.assertEqual(get_package_key_suffix('0.3.0.post1'), "")

    def test_non_marketing_release(self):
        """
        If a weekly release is passed to ``get_package_key_suffix``, "-testing"
        is returned.
        """
        self.assertEqual(get_package_key_suffix('0.3.0dev1'), "-testing")

    def test_pre_release(self):
        """
        If a pre-release is passed to ``get_package_key_suffix``, "-testing"
        is returned.
        """
        self.assertEqual(get_package_key_suffix('0.3.0pre1'), "-testing")
