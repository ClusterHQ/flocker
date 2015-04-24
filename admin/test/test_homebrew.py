# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
Tests for :module:`admin.homebrew`.
"""

from twisted.trial.unittest import SynchronousTestCase
from twisted.python.usage import UsageError

from admin.homebrew import HomebrewOptions

class HomebrewOptionsTests(SynchronousTestCase):
    """
    Tests for :class:`HomebrewOptions`.
    """

    def test_flocker_version_required(self):
          """
          The ``--flocker-version`` option is not required.
          """
          options = HomebrewOptions()
          self.assertRaises(
              UsageError,
              options.parseOptions, ['--sdist', 'mysdist'])

    def test_sdist_required(self):
        """
        The ``--sdist`` option is not required.
        """
        options = HomebrewOptions()
        self.assertRaises(
            UsageError,
            options.parseOptions, ['--flocker-version', '0.3.0'])

    def test_output_file_not_required(self):
        """
        The ``--output-file`` option is not required.
        """
        # Does not raise
        options = HomebrewOptions()
        options.parseOptions([
            '--flocker-version', '0.3.0',
            '--sdist', 'mysdist'])

# TODO make private methods private
# TODO release will have to use an sdist

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
