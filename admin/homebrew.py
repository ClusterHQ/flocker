#!/usr/bin/env python

# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Create a Homebrew recipe for Flocker, using the VERSION environment variable.

Inspired by https://github.com/tdsmith/labmisc/blob/master/mkpydeps.
"""

from os import environ
from json import load
from urllib2 import HTTPError, urlopen
from hashlib import sha1
from tl.eggdeps.graph import Graph


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


def get_version():
    """
    :return str: The contents of the "VERSION" environment variable.

    :raises Exception: If $VERSION is not set.
    """
    version = environ.get("VERSION")
    if version is None:
        raise Exception("Set the VERSION environment variable.")
    return version


def get_checksum(url):
    """
    Given the URL of a file, download that file and return its sha1 hash.

    :param unicode url: A URL of a file.

    :return str checksum: The sha1 hash of the file at ``url``.
    """
    try:
        download = urlopen(url)
    except HTTPError:
        raise Exception("No file available at " + url)

    checksum = sha1(download.read()).hexdigest()
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
        url = u"http://pypi.python.org/pypi/{name}/{version}/json".format(
              name=project_name,
              version=version)
        f = urlopen(url)
        pypi_information = load(f)
        f.close()
        resource_added = False
        for release in pypi_information['urls']:
            if release['packagetype'] == 'sdist':
                url = release['url']
                resource_added = True
                resources += resource_template.format(
                    project_name=project_name, url=release['url'],
                    checksum=get_checksum(url))
                break
        if not resource_added:
            raise Exception("sdist package not found for " + name)
    return resources


def main():
    """
    Print a Homebrew recipe for Flocker, using the VERSION environment
    variable.
    """
    version = get_version()
    url = (u"https://storage.googleapis.com/archive.clusterhq.com/"
           "downloads/flocker/Flocker-{version}.tar.gz").format(
               version=version)

    dependency_graph = get_dependency_graph(u"flocker")

    print u"""require "formula"

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
""".format(version=version, url=url, sha1=get_checksum(url),
           class_name=get_class_name(version),
           resources=get_resource_stanzas(dependency_graph),
           dependencies=get_formatted_dependency_list(dependency_graph))

if __name__ == "__main__":
    main()
