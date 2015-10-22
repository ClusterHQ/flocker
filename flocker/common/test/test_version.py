# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for :module:`flocker.docs.version`.
"""


from twisted.trial.unittest import SynchronousTestCase

try:
    from packaging.version import Version as PEP440Version
    PACKAGING_INSTALLED = True
except ImportError:
    PACKAGING_INSTALLED = False

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
            '0.1.1rc1': RPMVersion(version='0.1.1', release='0.rc.1'),
            '0.1.1': RPMVersion(version='0.1.1', release='1'),
            '0.2.0.dev1': RPMVersion(version='0.2.0', release='0.dev.1'),
            '0.2.0.dev2+99.g3d644b1':
                RPMVersion(version='0.2.0', release='0.dev.2.99.g3d644b1'),
            '0.2.0.dev3+100.g3d644b2.dirty': RPMVersion(
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
            make_rpm_version('0.1.2rcX')


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
    :param bool is_legacy: Whether the version is an old-style
        version. In particular, the version isn't normalized
        according to PEP440.
    """
    version = field(bytes, mandatory=True)
    flocker_version = field(FlockerVersion, mandatory=True)
    doc_version = field(bytes, mandatory=True)
    installable_version = field(bytes, mandatory=True)
    is_release = field(bool, mandatory=True)
    is_weekly_release = field(bool, mandatory=True)
    is_pre_release = field(bool, mandatory=True)
    is_legacy = field(bool, mandatory=True, initial=False)


def build_version_test(name, version_case):
    """
    Create a test case that checks that a given version
    is interpreted as expected.
    """
    class Tests(SynchronousTestCase):
        def test_flocker_version(self):
            """
            The parsed version matches the expected parsed version.
            """
            self.assertEqual(
                _parse_version(version_case.version),
                version_case.flocker_version,
                "Version doesn't match expected parsed version.",
            )

        def test_doc_version(self):
            """
            The calculated doc version matches the expected doc version.",
            """
            self.assertEqual(
                get_doc_version(version_case.version),
                version_case.doc_version,
                "Calculated doc version doesn't match expected doc version.",
            )

        def test_installable_version(self):
            """
            The calculated installable version matches the expected installable
            version.
            """
            self.assertEqual(
                get_installable_version(version_case.version),
                version_case.installable_version,
                "Calculated installable version doesn't match"
                "expected installable version.",)

        if version_case.is_legacy:
            test_installable_version.skip = (
                "Legacy version don't generate proper installable version."
            )

        def test_is_release(self):
            """
            ``is_release`` returns the expected value for the version.
            """
            self.assertEqual(
                is_release(version_case.version),
                version_case.is_release,
            )

        def test_is_weekly_release(self):
            """
            ``is_weekly_release`` returns the expected value for the version.
            """
            self.assertEqual(
                is_weekly_release(version_case.version),
                version_case.is_weekly_release,
            )

        def test_is_pre_release(self):
            """
            ``is_pre_release`` returns the expected value for the version.
            """
            self.assertEqual(
                is_pre_release(version_case.version),
                version_case.is_pre_release,
            )

        def test_pep_440(self):
            """
            The version is a valid PEP440 version.

            (``PEP440Version`` raises if provided an invalid version).
            """
            PEP440Version(version_case.version)

        def test_normalization(self):
            """
            The version number is normalized according to PEP440.
            """
            self.assertEqual(
                version_case.version,
                str(PEP440Version(version_case.version)),
                "Version isn't normalized.",
            )
        if version_case.is_legacy:
            test_normalization.skip = "Legacy version isn't normalized."

        if not PACKAGING_INSTALLED:
            test_normalization.skip = test_pep_440.skip = (
                "``packaing`` not installed."
            )

    Tests.__name__ = name
    return Tests


MarketingVersionTests = build_version_test(
    "MarketingVersionTests",
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
        version=b'0.3.2.dev1',
        flocker_version=FlockerVersion(
            major=b'0',
            minor=b'3',
            micro=b'2',
            weekly_release=b'1',
        ),
        doc_version=b'0.3.2.dev1',
        installable_version=b'0.3.2.dev1',
        is_release=False,
        is_weekly_release=True,
        is_pre_release=False,
    ),
)
PreReleaseTests = build_version_test(
    "PreReleaseTests",
    VersionCase(
        version=b'0.3.2rc1',
        flocker_version=FlockerVersion(
            major=b'0',
            minor=b'3',
            micro=b'2',
            pre_release=b'1',
        ),
        doc_version=b'0.3.2rc1',
        installable_version=b'0.3.2rc1',
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

# Legacy Version Tests
# These only test with an appended version.
LegacyPreReleaseTests = build_version_test(
    "LegacyPreReleaseTests",
    VersionCase(
        version=b'0.3.2pre11+1.gf661a6a',
        flocker_version=FlockerVersion(
            major=b'0',
            minor=b'3',
            micro=b'2',
            pre_release=b'11',
            commit_count=b'1',
            commit_hash=b'f661a6a',
        ),
        doc_version=b'0.3.2pre11+1.gf661a6a',
        installable_version=b'0.3.2pre11',
        is_release=False,
        is_weekly_release=False,
        is_pre_release=False,
        is_legacy=True,
    ),
)
LegacyDocReleaseTests = build_version_test(
    "LegacyPreReleaseTests",
    VersionCase(
        version=b'0.3.2+doc11.1.gf661a6a',
        flocker_version=FlockerVersion(
            major=b'0',
            minor=b'3',
            micro=b'2',
            documentation_revision=b'11',
            commit_count=b'1',
            commit_hash=b'f661a6a',
        ),
        doc_version=b'0.3.2+doc11.1.gf661a6a',
        installable_version=b'0.3.2',
        is_release=False,
        is_weekly_release=False,
        is_pre_release=False,
        is_legacy=True,
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
        self.assertEqual(get_pre_release('0.3.2rc3'), 3)


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
        self.assertEqual(target_release('0.3.2rc3'), '0.3.2')


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
        self.assertEqual(get_package_key_suffix('0.3.0.dev1'), "-testing")

    def test_pre_release(self):
        """
        If a pre-release is passed to ``get_package_key_suffix``, "-testing"
        is returned.
        """
        self.assertEqual(get_package_key_suffix('0.3.0rc1'), "-testing")
