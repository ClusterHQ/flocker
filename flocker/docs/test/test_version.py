# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for :module:`flocker.docs.version`.
"""


from twisted.trial.unittest import SynchronousTestCase

from .._version import (
    parse_version, FlockerVersion, UnparseableVersion,
    get_doc_version, get_installable_version, is_release, is_weekly_release,
)


class ParseVersionTests(SynchronousTestCase):
    """
    Tests for :function:`parse_version`.
    """
    def assertParsedVersion(self, version, **expected_parts):
        """
        Assert that :function:`parse_version` returns ``expected_parts``.
        The release is expected to be `0.3.2`.
        """
        parts = {
            'major': '0',
            'minor': '3',
            'micro': '2',
        }
        parts.update(expected_parts)
        self.assertEqual(parse_version(version), FlockerVersion(**parts))

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
        If an invalid vesion is passed to ``parse_version``,
        ``UnparseableVersion`` is raised.
        """
        self.assertRaises(UnparseableVersion, parse_version, 'unparseable')


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
        When the version is from a weekly release, it isn't a weekly release.
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

    def test_doc_dirty(self):
        """
        When the version is from a documentation weekly release but is dirty,
        it isn't a weekly release.
        """
        self.assertFalse(is_weekly_release('0.3.2+doc1-dirty'))
