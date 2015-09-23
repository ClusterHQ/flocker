# -*- test-case-name: admin.test.test_homebrew -*-
# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Create a Homebrew recipe for Flocker, using the VERSION environment variable.

Inspired by https://github.com/tdsmith/labmisc/blob/master/mkpydeps.
"""

import logging
import sys
from hashlib import sha1

from twisted.python.usage import Options, UsageError
from pkg_resources import parse_requirements

import requests
from requests_file import FileAdapter


def get_requirements(requirements_path):
    """
    Get the dependencies of an application from a :file:`requirements.txt`.

    :param FilePath requirements_path: The path to the requirements file.

    :return: List of requirements.
    :rtype: ``list`` of ``Requirement``s
    """
    return list(parse_requirements(requirements_path.getContent()))


def get_checksum(url):
    """
    Given the URL of a file, download that file and return its sha1 hash.

    :param bytes url: A URL of a file.

    :return str checksum: The sha1 hash of the file at ``url``.
    """
    session = requests.Session()
    # Tests use a local package repository
    session.mount('file://', FileAdapter())
    download = session.get(url, stream=True)
    download.raise_for_status()
    content = download.raw.read()

    return sha1(content).hexdigest()


def get_class_name(version):
    """
    The ruby class name depends on the Flocker version. For example for version
    0.3.0.dev1 the class name should be Flocker0.3.0.dev1.

    :param str version: The version of Flocker this recipe is for.

    :return unicode: The name of the ruby class needed if the file being
        created is called "flocker-$VERSION.rb".
    """
    class_name = list('Flocker' + version)
    disallowed_characters = ['-', '.', '+']
    characters = []

    for index, character in enumerate(class_name):
        if character not in disallowed_characters:
            if class_name[index - 1] in disallowed_characters:
                characters.append(character.upper())
            else:
                characters.append(character)

    return u''.join(characters)


def get_resources(requirements):
    """
    Get the URLs and checksums of Python dependencies.

    :param requirements: List of flocker dependencies.
    :type requirements: ``list`` of ``Requirement``s.

    :return list: Dictionaries mapping project names to URLs and checksums.
    """
    resources = []
    for requirement in sorted(requirements, key=lambda r: r.project_name):
        operator, version = requirement.specs[0]
        project_name = requirement.project_name
        url = b"https://pypi.python.org/pypi/{name}/{version}/json".format(
              name=project_name,
              version=version)
        r = requests.get(url)
        r.raise_for_status()
        pypi_information = r.json()
        for release in pypi_information['urls']:
            if release['packagetype'] == 'sdist':
                sdist_url = release['url']
                resources.append({
                    "project_name": project_name,
                    "url": sdist_url,
                    "checksum": get_checksum(sdist_url),
                })
                break
        else:
            raise Exception("sdist package not found for " + project_name)
    return resources


def format_resource_stanzas(resources):
    """
    Given resources, create stanzas for a recipe.

    :param resources: List of dictionaries mapping project names to urls and
        checksums.
    :return: Unicode representing resource stanzas.
    """
    stanzas = []
    stanza_template = u"""
  resource "{project_name}" do
    url "{url}"
    sha1 "{checksum}"
  end
"""
    for resource in resources:
        stanzas.append(stanza_template.format(
            project_name=resource['project_name'],
            url=resource['url'],
            checksum=resource['checksum']))
    return u''.join(stanzas)


def make_recipe(version, sdist_url, requirements_path):
    """
    Create a Homebrew recipe. This uses the network.

    :param version: The version of Flocker to create a recipe for.
    :param sdist_url: The URL of the source distribution of Flocker.
    :param FilePath: The path to the requirements file.

    :return unicode: A Homebrew recipe.
    """
    requirements = get_requirements(requirements_path)
    return get_recipe(
        sdist_url=sdist_url,
        sha1=get_checksum(url=sdist_url),
        class_name=get_class_name(version=version),
        resources=get_resources(requirements=requirements),
    )


def get_recipe(sdist_url, sha1, class_name, resources):
    """
    Create a Homebrew recipe. This does not use the network.

    :param sdist_url: The URL of the source distribution of Flocker.
    :param sha1: The checksum of ``sdist_url``.
    :param class_name: The recipe Ruby class name.
    :param resources: List of dictionaries mapping project names to urls and
        checksums or dependencies.

    :return unicode: A Homebrew recipe.
    """
    dependencies = [resource['project_name'] for resource in resources]

    return u"""\
require "formula"

class {class_name} < Formula
  homepage "https://clusterhq.com"
  url "{sdist_url}"
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
""".format(
            sdist_url=sdist_url,
            sha1=sha1,
            class_name=class_name,
            resources=format_resource_stanzas(resources),
            dependencies=u' '.join(dependencies))


class HomebrewOptions(Options):
    """
    Options for creating a Homebrew recipe.
    """
    optParameters = [
        ["flocker-version", None, None,
         "The version of Flocker to create a recipe for."],
        ["sdist", None, None,
         "URL to a source distribution of Flocker."],
        ["output-file", None, None,
         "The name of a file to output containing the recipe."],
    ]

    def parseArgs(self):
        if self['flocker-version'] is None:
            raise UsageError("`--flocker-version` must be specified.")

        if self['sdist'] is None:
            raise UsageError("`--sdist` must be specified.")

        if self['output-file'] is None:
            raise UsageError("`--output-file` must be specified.")


def main(args, base_path, top_level):
    """
    Create a Homebrew recipe.
    """
    options = HomebrewOptions()

    try:
        options.parseOptions(args)
    except UsageError as e:
        sys.stderr.write("%s: %s\n" % (base_path.basename(), e))
        raise SystemExit(1)

    logging.basicConfig(level=logging.INFO)
    version = options["flocker-version"]
    logging.info('Creating Homebrew recipe for version {}'.format(version))
    requirements_path = top_level.child('requirements.txt')
    recipe = make_recipe(
        version=version,
        sdist_url=options["sdist"],
        requirements_path=requirements_path,
    )

    with open(options["output-file"], 'wt') as f:
        f.write(recipe)


if __name__ == "__main__":
    from _preamble import TOPLEVEL, BASEPATH
    main(sys.argv[1:], top_level=TOPLEVEL, base_path=BASEPATH)
