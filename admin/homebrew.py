# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Create a Homebrew recipe for Flocker, using the VERSION environment variable.

Inspired by https://github.com/tdsmith/labmisc/blob/master/mkpydeps.
"""

import argparse
import logging
import sys
from os import environ
from json import load
from urllib2 import urlopen
from hashlib import sha1

from effect import sync_performer, TypeDispatcher
from characteristic import attributes
# TODO this will have to be a dev requirement if it isn't already
from tl.eggdeps.graph import Graph


@attributes([
    "flocker_version",
    "sdist",
])
class GetHomebrewRecipe(object):
    """
    Upload contents of a directory to S3, for given files.

    Note that this returns a list with the prefixes stripped.

    :ivar FilePath source_path: Prefix of files to be uploaded.
    :ivar bytes target_bucket: Name of bucket to upload file to.
    :ivar bytes target_key: Name S3 key to upload file to.
    :ivar list files: List of bytes, relative paths to files to upload.
    """


class FakeHomebrew(object):
    """
    Fake for homebrew
    """
    @sync_performer
    def _perform_get_homebrew_recipe(self, dispatcher, intent):
        return "Some recipe contents"

    def get_dispatcher(self):
        """
        Get an :module:`effect` dispatcher for interacting with this
        :class:`FakeAWS`.
        """
        return TypeDispatcher({
            GetHomebrewRecipe: self._perform_get_homebrew_recipe,
        })

# todo main() should use this, change buildbot to use this
def perform_get_homebrew_recipe(dispatcher, intent):
    pass

homebrew_dispatcher = TypeDispatcher({
    GetHomebrewRecipe: perform_get_homebrew_recipe,
})

def get_dependency_graph(application):
    """
    Get the dependencies of an application.

    :param unicode application: The name of an application to get the
        dependencies of.

    :return tl.eggdeps.graph.Graph: Graph of Python dependencies, not
        including ``application``.
    """
    dependency_graph = Graph()
    dependency_graph.from_specifications([application])
    # We don't want flocker to require flocker, so we pop "application" out
    # of the graph
    dependency_graph.pop(application)
    return dependency_graph


def get_checksum(url):
    """
    Given the URL of a file, download that file and return its sha1 hash.

    :param bytes url: A URL of a file.

    :return str checksum: The sha1 hash of the file at ``url``.
    """
    logging.info('Downloading {}'.format(url))
    download = urlopen(url)
    try:
        checksum = sha1(download.read()).hexdigest()
    finally:
        download.close()
    return checksum


def get_class_name(version):
    """
    The ruby class name depends on the Flocker version. For example for version
    0.3.0dev1 the class name should be Flocker0.3.0dev1.

    :param str version: The version of Flocker this recipe is for.

    :return str: The name of the ruby class needed if the file being created
        is called "flocker-$VERSION.rb".
    """
    class_name = 'Flocker' + version
    for disallowed_character in ['-', '.']:
        class_name = class_name.replace(disallowed_character, '')
    return class_name


def get_formatted_dependency_list(dependency_graph):
    """
    :param tl.eggdeps.graph.Graph dependency_graph: Graph of Python
        dependencies.

    :return unicode: Space separated list of dependency names.
    """
    dependencies = []
    for name, node in sorted(dependency_graph.iteritems()):
        requirement = node.dist.as_requirement()
        dependencies.append(requirement.project_name)
    return u' '.join(dependencies)


def get_resource_stanzas(dependency_graph):
    """
    :param tl.eggdeps.graph.Graph dependency_graph: Graph of Python
        dependencies.

    :return unicode: The part of the Homebrew recipe which defines the Python
        packages to install.
    """
    resources = u""
    resource_template = u"""
  resource "{project_name}" do
    url "{url}"
    sha1 "{checksum}"
  end
"""
    for name, node in sorted(dependency_graph.iteritems()):
        requirement = node.dist.as_requirement()
        operator, version = requirement.specs[0]
        project_name = requirement.project_name
        url = b"http://pypi.python.org/pypi/{name}/{version}/json".format(
              name=project_name,
              version=version)
        f = urlopen(url)
        pypi_information = load(f)
        f.close()
        for release in pypi_information['urls']:
            if release['packagetype'] == 'sdist':
                url = release['url']
                resources += resource_template.format(
                    project_name=project_name, url=release['url'],
                    checksum=get_checksum(url))
                break
        else:
            raise Exception("sdist package not found for " + name)
    return resources


def main():
    """
    # TODO docstring should mention the --output-file
    # TODO separate this out into a more standard Options class using twisted's
    # options
    # TODO create a function to get the string
    # TODO tests for some things, including the options
    # TODO look at using homebrew-poet
    Print a Homebrew recipe for the Flocker distribution.

    The version for the recipe must be provided in the environment
    variable ``VERSION``.

    If the command is called with a single argument, the argument
    provides a URL to retrieve the initial source distribution archive.

    If no command line argument is provided, use the standard release
    location for the indicated version.
    """
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(
        description='Create a Homebrew recipe from a source distribution.')
    parser.add_argument(
        '--flocker-version', help='version number for the Homebrew recipe'
        ' (either this argument or the environment variable VERSION must be'
        ' provided)')
    parser.add_argument(
        '--sdist', help='URL of the source distribution')
    parser.add_argument(
        '--output-file',
        help='filename for created Homebrew recipe (default: stdout)')
    args = parser.parse_args()

    # If version not supplied, for backwards-compatibility, get it from
    # the environment variable VERSION.
    version = args.flocker_version
    if version is None:
        version = environ.get('VERSION')
        if version is None:
            parser.print_help()
            sys.exit(1)
    logging.info('Creating Homebrew recipe for version {}'.format(version))

    # If url not supplied, for backwards-compatibility, use the Google
    # Storage location specified in the release process.
    url = args.sdist
    if url is None:
        url = (b"https://storage.googleapis.com/archive.clusterhq.com/"
               "downloads/flocker/Flocker-{version}.tar.gz").format(
                   version=version)

    dependency_graph = get_dependency_graph(u"flocker")

    recipe = u"""require "formula"

class {class_name} < Formula
  homepage "https://clusterhq.com"
  url "{url}"
  sha1 "{sha1}"
  depends_on :python if MacOS.version <= :snow_leopard
{resources}
  def install
    ENV.prepend_create_path "PYTHONPATH", "#{{libexec}}/vendor/lib/python2.7/site-packages"
    %w[{dependencies}].each do |r|
      resource(r).stage do
        system "python", *Language::Python.setup_install_args(libexec/"vendor")
      end
    end

    ENV.prepend_create_path "PYTHONPATH", libexec/"lib/python2.7/site-packages"
    system "python", *Language::Python.setup_install_args(libexec)

    bin.install Dir["#{{libexec}}/bin/*"]
    bin.env_script_all_files(libexec/"bin", :PYTHONPATH => ENV["PYTHONPATH"])
  end

  test do
    system "#{{bin}}/flocker-deploy", "--version"
  end
end
""".format(url=url, sha1=get_checksum(url),
           class_name=get_class_name(version),
           resources=get_resource_stanzas(dependency_graph),
           dependencies=get_formatted_dependency_list(dependency_graph))

    # If output-file not supplied, print to stdout.
    filename = args.output_file
    if filename is None:
        sys.stdout.write(recipe)
    else:
        logging.info('Writing Homebrew recipe to file "{}"'.format(filename))
        with open(filename, 'wt') as f:
            f.write(recipe)


if __name__ == "__main__":
    main()
