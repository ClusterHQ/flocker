# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
Tests for :module:`admin.vagrant`.
"""

from twisted.trial.unittest import SynchronousTestCase
from twisted.python.filepath import FilePath
from twisted.python.usage import UsageError

from admin.homebrew import (
    box_metadata, BuildOptions)

from flocker import __version__ as flocker_version

class HomebrewOptionsTests(SynchronousTestCase):
    """
    Tests for :func:`box_metadata`.
    """

class GetChecksumTests(SynchronousTestCase):
    pass

class GetDependencyGraphTests(SynchronousTestCase):
    pass

class GetClassNameTests(SynchronousTestCase):
    def test_flocker_version(self):
        pass

    def test_unexpected_fails(self):
        """
        The given version must be a valid Flocker version.
        """

class GetFormattedDependencyListTests(SynchronousTestCase):
    pass

class GetResourceStanzasTests(SynchronousTestCase):
    pass
