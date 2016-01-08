# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for top-level ``flocker`` package.
"""

from sys import executable
from subprocess import check_output, STDOUT

from twisted.python.filepath import FilePath

import flocker
from ..testtools import TestCase


class WarningsTests(TestCase):
    """
    Tests for warning suppression.
    """
    def test_warnings_suppressed(self):
        """
        Warnings are suppressed for processes that import flocker.
        """
        root = FilePath(flocker.__file__)
        result = check_output(
            [executable, b"-c", (b"import flocker; import warnings; " +
                                 b"warnings.warn('ohno')")],
            stderr=STDOUT,
            # Make sure we can import flocker package:
            cwd=root.parent().parent().path)
        self.assertEqual(result, b"")
