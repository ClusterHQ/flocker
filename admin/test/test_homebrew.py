# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
Tests for :module:`admin.homebrew`.
"""

from twisted.python.filepath import FilePath
from twisted.trial.unittest import SynchronousTestCase
from twisted.python.usage import UsageError

from requests.exceptions import HTTPError

from admin.homebrew import (
    HomebrewOptions, get_checksum, get_dependency_graph, get_class_name,
    format_resource_stanzas,
)


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
    def test_checksum(self):
        """
        The sha1 hash of a file at a given URI is returned.
        """
        source_repo = FilePath(self.mktemp())
        source_repo.makedirs()
        file = source_repo.child('example_file')
        file.setContent("Some content")

        uri = 'file://' + file.path
        # TODO Make get_checksum take URI not URL
        self.assertEqual(
            '9f1a6ecf74e9f9b1ae52e8eb581d420e63e8453a',
            get_checksum(url=uri))

    def test_file_not_available(self):
        """
        If a requested file is not available in the repository, a 404 error is
        raised.
        """
        with self.assertRaises(HTTPError) as exception:
            get_checksum(url='file://' + FilePath(self.mktemp()).path)

        self.assertEqual(404, exception.exception.response.status_code)


class GetDependencyGraphTests(SynchronousTestCase):
    """
    Tests for X.
    """
    def test_get_dependency_graph(self):
        graph = get_dependency_graph(u'flocker')
        # We can be sure that flocker is installed if we are running this,
        # and pretty sure that setuptools is a dependency with no dependencies
        # of its own.
        # Perhaps a better test would installe a canned package.
        self.assertEqual(graph['setuptools'], {})

    def test_application_removed(self):
        """
        Applications cannot depend on themselves so they are not in the graph.
        """
        self.assertNotIn(u'flocker', get_dependency_graph(u'flocker'))


class GetClassNameTests(SynchronousTestCase):
    """
    Tests for X.
    """
    def test_disallowed_characters_removed(self):
        """
        Hyphens and periods are removed.
        """
        self.assertEqual(
            get_class_name(version='0.3.0-444-05215b'),
            'Flocker03044405215b'
        )

    def test_caps_after_disallowed(self):
        """
        If there is a letter following a disallowed character then it is
        capitalised.
        """
        self.assertEqual(
            get_class_name(version='0.3.0-444-g05215b'),
            'Flocker030444G05215b'
        )

    def test_disallowed_at_end(self):
        """
        If there is a letter following a disallowed character then it is
        capitalised.
        """
        self.assertEqual(
            get_class_name(version='0.3.0-444-g05215b-'),
            'Flocker030444G05215b'
        )

class FormatResourceStanzasTests(SynchronousTestCase):
    """
    Tests for X.
    """
    def test_two_resources(self):
        resources = [{
            "project_name": "six",
            "url": "https://example.com/six/six-1.9.0.tar.gz",
            "checksum": "d168e6d01f0900875c6ecebc97da72d0fda31129",
        },
        {
            "project_name": "treq",
            "url": "https://example.com/treq/treq-0.2.1.tar.gz",
            "checksum": "fc19b107d0cd6660f797ec6f82c3a61d5e2a768a",
        },
        ]
        expected = u"""
  resource "six" do
    url "https://example.com/six/six-1.9.0.tar.gz"
    sha1 "d168e6d01f0900875c6ecebc97da72d0fda31129"
  end

  resource "treq" do
    url "https://example.com/treq/treq-0.2.1.tar.gz"
    sha1 "fc19b107d0cd6660f797ec6f82c3a61d5e2a768a"
  end
"""
        self.assertEqual(expected, format_resource_stanzas(resources))

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
