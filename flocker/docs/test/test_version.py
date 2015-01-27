# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Test for :module:`flocker.docs.version`.
"""


from twisted.trial.unittest import SynchronousTestCase

from .._version import get_version


class GetVersionTests(SynchronousTestCase):
    """
    Test for :function:`get_version`.
    """

    def test_release(self):
        """
        When the version is from a release, the version is left unchanged.
        """
        self.assertEqual(get_version('0.3.2'), '0.3.2')

    def test_development_vesion(self):
        """
        When the version is from a development version, the version is left
        unchanged.
        """
        self.assertEqual(get_version('0.3.2-1-gf661a6a'), '0.3.2-1-gf661a6a')

    def test_dirty(self):
        """
        When the version is dirty, the version is left unchanged.
        """
        self.assertEqual(get_version('0.3.2-1-gf661a6a-dirty'),
                         '0.3.2-1-gf661a6a-dirty')

    def test_doc(self):
        """
        When the version is from a doc release, the trailing '+doc.X' is
        stripped.
        """
        self.assertEqual(get_version('0.3.2+doc.11'), '0.3.2')

    def test_doc_dirty(self):
        """
        When the version is from a doc release but is dirty, the version is
        left unchanged.
        """
        self.assertEqual(get_version('0.3.2+doc.0.dirty'),
                         '0.3.2+doc.0.dirty')
