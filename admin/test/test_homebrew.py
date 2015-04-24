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

    def test_output_file_required(self):
        """
        The ``--output-file`` option is required.
        """
        options = HomebrewOptions()
        self.assertRaises(
            UsageError,
            options.parseOptions,
            ['--flocker-version', '0.3.0',
             '--sdist', 'mysdist'])

# TODO make private methods private
# TODO release will have to use an sdist
# TODO update buildbot to call wrapper script
# TODO one function called by main which gets everything and returns a recipe
# this will help with faking

class GetChecksumTests(SynchronousTestCase):
    """
    Tests for X.
    """
    # TODO use requests
    # test with local file, like with RPMs
    pass

class GetDependencyGraphTests(SynchronousTestCase):
    """
    Tests for X.
    """
    pass

class GetClassNameTests(SynchronousTestCase):
    """
    Tests for X.
    """
    def test_disallowed_characters_removed(self):
        pass

class GetFormattedDependencyListTests(SynchronousTestCase):
    """
    Tests for X.
    """
    # TODO this should return a list which is later formatted

class GetResourceStanzasTests(SynchronousTestCase):
    """
    Tests for X.
    """
    # TODO should return a dictionary of project names to URLs and Checksums
    # get_recipe should turn this dictionary into string
    def test_package_not_found(self):
        pass
