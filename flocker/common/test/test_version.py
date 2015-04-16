# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for :module:`flocker.docs.version`.
"""


from twisted.trial.unittest import SynchronousTestCase

from ..version import (
    _parse_version, FlockerVersion,
    get_doc_version, get_installable_version, get_pre_release,
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
            '0.1.0-99-g3d644b1': RPMVersion(
                version='0.1.0', release='1.99.g3d644b1'),
            '0.1.1pre1': RPMVersion(version='0.1.1', release='0.pre.1'),
            '0.1.1': RPMVersion(version='0.1.1', release='1'),
            '0.2.0dev1': RPMVersion(version='0.2.0', release='0.dev.1'),
            '0.2.0dev2-99-g3d644b1':
                RPMVersion(version='0.2.0', release='0.dev.2.99.g3d644b1'),
            '0.2.0dev3-100-g3d644b2-dirty': RPMVersion(
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


class ParseVersionTests(SynchronousTestCase):
    """
    Tests for :function:`_parse_version`.
    """
    def assertParsedVersion(self, version, **expected_parts):
        """
        Assert that :function:`_parse_version` returns ``expected_parts``.
        The release is expected to be `0.3.2`.
        """
        parts = {
            'major': '0',
            'minor': '3',
            'micro': '2',
        }
        parts.update(expected_parts)
        self.assertEqual(_parse_version(version), FlockerVersion(**parts))

    def test_marketing_release(self):
        """
        When the version is from a marketing release, the documentation version
        is left unchanged.
        """
        self.assertParsedVersion('0.3.2')

    def test_weekly_release(self):
        """
        When the version is from a weekly release, the documentation version
        is left unchanged.
        """
        self.assertParsedVersion('0.3.2dev1',
                                 weekly_release='1')

    def test_pre_release(self):
        """
        When the version is from a pre-release, the documentation version
        is left unchanged.
        """
        self.assertParsedVersion('0.3.2pre1',
                                 pre_release='1')

    def test_development_vesion(self):
        """
        When the version is from a development version, the documentation
        version is left unchanged.
        """
        self.assertParsedVersion('0.3.2-1-gf661a6a',
                                 commit_count='1',
                                 commit_hash='f661a6a')

    def test_dirty(self):
        """
        When the version is dirty, the documentation version is left unchanged.
        """
        self.assertParsedVersion('0.3.2-1-gf661a6a-dirty',
                                 commit_count='1',
                                 commit_hash='f661a6a',
                                 dirty='-dirty')

    def test_doc(self):
        """
        When the documentation version is from a documentation release, the
        trailing '+docX' is stripped.
        """
        self.assertParsedVersion('0.3.2+doc11',
                                 documentation_revision='11')

    def test_doc_dirty(self):
        """
        When the version is from a documentation release but is dirty, the
        documentation version is left unchanged.
        """
        self.assertParsedVersion('0.3.2+doc11-dirty',
                                 documentation_revision='11',
                                 dirty='-dirty')

    def test_invalid_Version(self):
        """
        If an invalid vesion is passed to ``_parse_version``,
        ``UnparseableVersion`` is raised.
        """
        self.assertRaises(UnparseableVersion, _parse_version, 'unparseable')


class GetDocVersionTests(SynchronousTestCase):
    """
    Tests for :function:`get_doc_version`.
    """

    def test_marketing_release(self):
        """
        When the version is from a marketing release, the documentation version
        is left unchanged.
        """
        self.assertEqual(get_doc_version('0.3.2'), '0.3.2')

    def test_weekly_release(self):
        """
        When the version is from a weekly release, the documentation version
        is left unchanged.
        """
        self.assertEqual(get_doc_version('0.3.2dev1'), '0.3.2dev1')

    def test_pre_release(self):
        """
        When the version is from a pre-release, the documentation version
        is left unchanged.
        """
        self.assertEqual(get_doc_version('0.3.2pre1'), '0.3.2pre1')

    def test_development_vesion(self):
        """
        When the version is from a development version, the documentation
        version is left unchanged.
        """
        self.assertEqual(get_doc_version('0.3.2-1-gf661a6a'),
                         '0.3.2-1-gf661a6a')

    def test_dirty(self):
        """
        When the version is dirty, the documentation version is left unchanged.
        """
        self.assertEqual(get_doc_version('0.3.2-1-gf661a6a-dirty'),
                         '0.3.2-1-gf661a6a-dirty')

    def test_doc(self):
        """
        When the documentation version is from a documentation release, the
        trailing '+docX' is stripped.
        """
        self.assertEqual(get_doc_version('0.3.2+doc11'), '0.3.2')

    def test_doc_dirty(self):
        """
        When the version is from a documentation release but is dirty, the
        documentation version is left unchanged.
        """
        self.assertEqual(get_doc_version('0.3.2+doc1-dirty'),
                         '0.3.2+doc1-dirty')


class GetInstallableVersionTests(SynchronousTestCase):
    """
    Tests for :function:`get_installable_version`.
    """

    def test_marketing_release(self):
        """
        When the version is from a marketing release, the installable version
        is left unchanged.
        """
        self.assertEqual(get_installable_version('0.3.2'), '0.3.2')

    def test_weekly_release(self):
        """
        When the version is from a weekly release, the installable version
        is left unchanged.
        """
        self.assertEqual(get_installable_version('0.3.2dev1'), '0.3.2dev1')

    def test_pre_release(self):
        """
        When the version is from a pre-release, the installable version
        is left unchanged.
        """
        self.assertEqual(get_installable_version('0.3.2pre1'), '0.3.2pre1')

    def test_development_version(self):
        """
        When the version is from a development version, the installable
        version is changed to the latest marketing release.
        """
        self.assertEqual(get_installable_version('0.3.2-1-gf661a6a'), '0.3.2')

    def test_dirty(self):
        """
        When the version is dirty, the installable version is changed to the
        latest marketing release.
        """
        self.assertEqual(get_installable_version('0.3.2-1-gf661a6a-dirty'),
                         '0.3.2')

    def test_doc(self):
        """
        When the documentation version is from a documentation release, the
        trailing '+docX' is stripped.
        """
        self.assertEqual(get_installable_version('0.3.2+doc11'), '0.3.2')

    def test_doc_dirty(self):
        """
        When the version is from a documentation release but is dirty, the
        installable version is changed to the latest marketing release.
        """
        self.assertEqual(get_installable_version('0.3.2+doc1-dirty'), '0.3.2')


class IsReleaseTests(SynchronousTestCase):
    """
    Tests for :function:`is_release`.
    """

    def test_marketing_release(self):
        """
        When the version is from a marketing release, it is a release.
        """
        self.assertTrue(is_release('0.3.2'))

    def test_weekly_release(self):
        """
        When the version is from a weekly release, it isn't a release.
        """
        self.assertFalse(is_release('0.3.2dev1'))

    def test_pre_release(self):
        """
        When the version is from a pre-release, it isn't a release.
        """
        self.assertFalse(is_release('0.3.2pre1'))

    def test_development_version(self):
        """
        When the version is from a development version, it isn't a release.
        """
        self.assertFalse(is_release('0.3.2-1-gf661a6a'))

    def test_dirty(self):
        """
        When the version is dirty, it isn't a release.
        """
        self.assertFalse(is_release('0.3.2-1-gf661a6a-dirty'))

    def test_doc(self):
        """
        When the documentation version is from a documentation release, it is a
        release.
        """
        self.assertTrue(is_release('0.3.2+doc11'))

    def test_doc_dirty(self):
        """
        When the version is from a documentation release but is dirty, it isn't
        a release.
        """
        self.assertFalse(is_release('0.3.2+doc1-dirty'))


class IsWeeklyReleaseTests(SynchronousTestCase):
    """
    Tests for :function:`is_weekly_release`.
    """

    def test_marketing_release(self):
        """
        When the version is from a marketing release, it isn't a weekly
        release.
        """
        self.assertFalse(is_weekly_release('0.3.2'))

    def test_weekly_release(self):
        """
        When the version is from a weekly release, it is a weekly release.
        """
        self.assertTrue(is_weekly_release('0.3.2dev1'))

    def test_pre_release(self):
        """
        When the version is from a pre-release, it isn't a weekly release.
        """
        self.assertFalse(is_weekly_release('0.3.2pre1'))

    def test_development_vesion(self):
        """
        When the version is from a development version, it isn't a weekly
        release.
        """
        self.assertFalse(is_weekly_release('0.3.2-1-gf661a6a'))

    def test_dirty(self):
        """
        When the version is dirty, it isn't a weekly release.
        """
        self.assertFalse(is_weekly_release('0.3.2-1-gf661a6a-dirty'))

    def test_doc(self):
        """
        When the documentation version is from a documentation release,
        it isn't a weekly release.
        """
        self.assertFalse(is_weekly_release('0.3.2+doc11'))

    def test_weekly_dirty(self):
        """
        When the version is from a weekly release but is dirty, it isn't a
        weekly release.
        """
        self.assertFalse(is_weekly_release('0.3.2dev1-dirty'))


class IsPreReleaseTests(SynchronousTestCase):
    """
    Tests for :function:`is_pre_release`.
    """

    def test_marketing_release(self):
        """
        When the version is from a marketing release, it isn't a pre-release.
        """
        self.assertFalse(is_pre_release('0.3.2'))

    def test_weekly_release(self):
        """
        When the version is from a weekly release, it isn't a pre-release.
        """
        self.assertFalse(is_pre_release('0.3.2dev1'))

    def test_pre_release(self):
        """
        When the version is from a pre-release, it is a pre-release.
        """
        self.assertTrue(is_pre_release('0.3.2pre1'))

    def test_development_vesion(self):
        """
        When the version is from a development version, it isn't a pre-release.
        """
        self.assertFalse(is_pre_release('0.3.2-1-gf661a6a'))

    def test_dirty(self):
        """
        When the version is dirty, it isn't a pre-release.
        """
        self.assertFalse(is_pre_release('0.3.2-1-gf661a6a-dirty'))

    def test_doc(self):
        """
        When the documentation version is from a documentation release,
        it isn't a pre-release.
        """
        self.assertFalse(is_pre_release('0.3.2+doc11'))

    def test_pre_release_dirty(self):
        """
        When the version is from a pre-release but is dirty, it isn't a
        pre-release.
        """
        self.assertFalse(is_pre_release('0.3.2pre1-dirty'))


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
