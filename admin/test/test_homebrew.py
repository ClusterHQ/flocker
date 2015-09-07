# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
Tests for :module:`admin.homebrew`.
"""

import gzip

from twisted.python.filepath import FilePath
from twisted.trial.unittest import SynchronousTestCase
from twisted.python.usage import UsageError

from requests.exceptions import HTTPError
from pkg_resources import Requirement

from admin.homebrew import (
    HomebrewOptions, get_checksum, get_requirements, get_class_name,
    format_resource_stanzas, get_recipe,
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


class GetChecksumTests(SynchronousTestCase):
    """
    Tests for :func:`get_checksum`.
    """
    def test_checksum(self):
        """
        The sha1 hash of a file at a given URI is returned.
        """
        source_repo = FilePath(self.mktemp())
        source_repo.makedirs()
        example_file = source_repo.child('example_file')
        example_file.setContent("Some content")
        uri = 'file://' + example_file.path
        self.assertEqual(
            '9f1a6ecf74e9f9b1ae52e8eb581d420e63e8453a',
            get_checksum(url=uri))

    def test_gzip(self):
        """
        The sha1 hash of a gzip and not its unzipped content is returned.
        """
        source_repo = FilePath(self.mktemp())
        source_repo.makedirs()
        example_file = source_repo.child('example_gzip.tar.gz')
        # Set mtime else a timestamp of the current time will be used,
        # making the assertion value change.
        gzip_file = gzip.GzipFile(
            filename=example_file.path, mode="wb", mtime=0)
        self.addCleanup(gzip_file.close)
        gzip_file.write("Some content")
        uri = 'file://' + example_file.path

        self.assertEqual(
            'da39a3ee5e6b4b0d3255bfef95601890afd80709',
            get_checksum(url=uri))

    def test_file_not_available(self):
        """
        If a requested file is not available in the repository, a 404 error is
        raised.
        """
        with self.assertRaises(HTTPError) as exception:
            get_checksum(url='file://' + FilePath(self.mktemp()).path)

        self.assertEqual(404, exception.exception.response.status_code)


class GetRequirementsTests(SynchronousTestCase):
    """
    Tests for :func:`get_requirements`.
    """
    def test_get_requirements(self):
        """
        It is possible to get a list of requirements from a requirements.txt
        file.
        """
        requirements_path = FilePath(self.mktemp())
        requirements_path.setContent(
            '\n'.join(["eliot==0.7.0", "Twisted==15.2.0"])
        )

        requirements = get_requirements(requirements_path)

        self.assertEqual(
            requirements,
            [
                Requirement.parse("eliot==0.7.0"),
                Requirement.parse("Twisted==15.2.0"),
            ],
        )


class GetClassNameTests(SynchronousTestCase):
    """
    Tests for :func:`get_class_name`.
    """
    def test_disallowed_characters_removed(self):
        """
        Hyphens and periods are removed.
        """
        self.assertEqual(
            get_class_name(version='0.3.0-444-05215b'),
            'Flocker03044405215b')

    def test_caps_after_disallowed(self):
        """
        If there is a letter following a disallowed character then it is
        capitalised.
        """
        self.assertEqual(
            get_class_name(version='0.3.0-444-g05215b'),
            'Flocker030444G05215b')

    def test_disallowed_at_end(self):
        """
        If there is a disallowed character at the end it is removed.
        """
        self.assertEqual(
            get_class_name(version='0.3.0-444-g05215b-'),
            'Flocker030444G05215b')


class FormatResourceStanzasTests(SynchronousTestCase):
    """
    Tests for :func:`format_resource_stanzas`.
    """
    def test_two_resources(self):
        """
        Newline separated resource stanzas are returned.
        """
        resources = [
            {
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


class GetRecipeTests(SynchronousTestCase):
    """
    Tests for :func:`get_recipe`.
    """
    def test_get_recipe(self):
        """
        A Homebrew recipe is returned. That this works is tested from
        ..testbrew.
        """
        resources = [{
            "project_name": "six",
            "url": "https://example.com/six/six-1.9.0.tar.gz",
            "checksum": "d168e6d01f0900875c6ecebc97da72d0fda31129",
        }]
        recipe = get_recipe(
            sdist_url="https://example.com/flocker_sdist",
            sha1="fc19b107d0cd6660f797ec6f82c3a61d5e2a768a",
            class_name="Flocker030",
            resources=resources,
        )
        expected = u"""require "formula"

class Flocker030 < Formula
  homepage "https://clusterhq.com"
  url "https://example.com/flocker_sdist"
  sha1 "fc19b107d0cd6660f797ec6f82c3a61d5e2a768a"
  depends_on :python if MacOS.version <= :snow_leopard

  resource "six" do
    url "https://example.com/six/six-1.9.0.tar.gz"
    sha1 "d168e6d01f0900875c6ecebc97da72d0fda31129"
  end

  def install
    ENV.prepend_create_path "PYTHONPATH", "#{libexec}/vendor/lib/python2.7/site-packages"
    %w[six].each do |r|
      resource(r).stage do
        system "python", *Language::Python.setup_install_args(libexec/"vendor")
      end
    end

    ENV.prepend_create_path "PYTHONPATH", libexec/"lib/python2.7/site-packages"
    system "python", *Language::Python.setup_install_args(libexec)

    bin.install Dir["#{libexec}/bin/*"]
    bin.env_script_all_files(libexec/"bin", :PYTHONPATH => ENV["PYTHONPATH"])
  end

  test do
    system "#{bin}/flocker-deploy", "--version"
  end
end
"""
        self.assertEqual(recipe, expected)
