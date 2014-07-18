"""
Tests for top-level ``flocker`` package.
"""

from sys import executable
from subprocess import check_output, STDOUT

from twisted.trial.unittest import SynchronousTestCase

class WarningsTests(SynchronousTestCase):
    """
    Tests for warning suppression.
    """
    def test_warnings_suppressed(self):
        """
        Warnings are suppressed for processes that import flocker.
        """
        result = check_output(
            [executable, b"-c", (b"import flocker; import warnings; " +
                                 b"warnings.warn(Warning())")],
            stderr=STDOUT)
        self.assertEqual(result, b"")
