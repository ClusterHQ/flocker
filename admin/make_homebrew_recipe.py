#!/usr/bin/env python

# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Create a Homebrew recipe for Flocker, using the VERSION environment variable.

Invoke using e.g.:
  $ export VERSION=0.1.2
  $ ./make_homebrew_recipe.py > > flocker-${VERSION}.rb

Inspired by https://github.com/tdsmith/labmisc/blob/master/mkpydeps.
"""

from os import environ
from json import load
from urllib2 import urlopen
from hashlib import sha1
from tl.eggdeps.graph import Graph

version = environ.get("VERSION")
if version is None:
    raise Exception("Set the VERSION environment variable.")

url = ("http://storage.googleapis.com/archive.clusterhq.com/"
       "downloads/flocker/Flocker-{version}.tar.gz").format(version=version)
tarball = urlopen(url)
checksum = sha1(tarball.read()).hexdigest()
tarball.close()

class_name = 'Flocker' + version
for disallowed_character in ['-', '.']:
    class_name = class_name.replace(disallowed_character, '')

resources = []
graph = Graph()
graph.from_specifications(["flocker"])
dependencies = []
for name, node in sorted(graph.iteritems()):
    if name == "flocker":
        continue
    else:
        requirement = node.dist.as_requirement()
        operator, version = requirement.specs[0]
        project_name = requirement.project_name
        dependencies.append(project_name)
        url = "http://pypi.python.org/pypi/{name}/{version}/json".format(
                name=project_name,
                version=version)
        f = urlopen(url)
        pypi_information = load(f)
        f.close()
        for release in pypi_information['urls']:
            if release['packagetype'] == 'sdist':
                url = release['url']
                sdist = urlopen(url)
                checksum = sha1(sdist.read()).hexdigest()
                sdist.close()

                resource = """
  resource "{project_name}" do
    url "{url}"
    sha1 "{checksum}"
  end
""".format(project_name=project_name, url=url, checksum=checksum)
                resources.append(resource)
                break

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
""".format(version=version, url=url, sha1=checksum, class_name=class_name,
           resources=''.join(resources), dependencies=' '.join(dependencies))
