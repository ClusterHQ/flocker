#!/usr/bin/env python

# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Create a Homebrew recipe for Flocker, using the VERSION environment variable.

Inspired by https://github.com/tdsmith/labmisc/blob/master/mkpydeps.
"""

from os import environ
from json import load
from urllib2 import urlopen
from hashlib import sha1
from tl.eggdeps.graph import Graph

# TODO return docs

def get_dependency_graph(application_name):
    """
    TODO
    """
    dependency_graph = Graph()
    dependency_graph.from_specifications([application_name])
    dependency_graph.pop(application_name, None)
    return dependency_graph


def get_version():
    """
    TODO
    """
    version = environ.get("VERSION")
    if version is None:
        raise Exception("Set the VERSION environment variable.")
    return version


def get_checksum(url):
    """
    Given the URL of a file, download that file and return its sha1 hash.

    :param unicode url: The URL of a file.
    """
    download = urlopen(url)
    checksum = sha1(download.read()).hexdigest()
    download.close()
    return checksum


def get_class_name(version):
    """
    The ruby class name depends on the Flocker version. For example for version
    0.3.0dev1 the class name should be Flocker0.3.0dev1.

    :param unicode version: The version of Flocker this recipe is for.
    """
    class_name = 'Flocker' + version
    for disallowed_character in ['-', '.']:
        class_name = class_name.replace(disallowed_character, '')
    return class_name


def get_formatted_dependency_list(dependency_graph):
    """
    TODO
    """
    dependencies = []
    for name, node in sorted(dependency_graph.iteritems()):
        requirement = node.dist.as_requirement()
        dependencies.append(requirement.project_name)
    return ' '.join(dependencies)


def get_resource_stanzas(dependency_graph):
    """
    Create the part of the Homebrew recipe which defines the python packages
    to install.

    :param tl.eggdeps.graph.Graph dependency_graph: Graph of Python
        dependencies.
    """
    resources = ""
    resource_template = """
  resource "{project_name}" do
    url "{url}"
    sha1 "{checksum}"
  end
"""
    for name, node in sorted(dependency_graph.iteritems()):
        requirement = node.dist.as_requirement()
        operator, version = requirement.specs[0]
        project_name = requirement.project_name
        url = "http://pypi.python.org/pypi/{name}/{version}/json".format(
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
    return resources


def main():
    version = get_version()
    url = ("https://storage.googleapis.com/archive.clusterhq.com/"
           "downloads/flocker/Flocker-{version}.tar.gz").format(
           version=version)

    dependency_graph = get_dependency_graph("flocker")

    print """require "formula"

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
