# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for top-level ``flocker`` package.
"""

from sys import executable
from subprocess import check_output, STDOUT

from twisted.trial.unittest import SynchronousTestCase
from twisted.python.filepath import FilePath

import flocker


class WarningsTests(SynchronousTestCase):
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
