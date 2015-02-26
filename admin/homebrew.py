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

# TODO add vmfusion to setup.py and google doc in appropriate sections
from vmfusion import vmrun

from flocker.provision._install import run, Run, Put


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

    :param bytes url: A URL of a file.

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
        url = b"http://pypi.python.org/pypi/{name}/{version}/json".format(
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


def create_recipe(version):
    """
    This creates a recipe for a version of Flocker available on GCS which is
    also installed in the current Python environment.

    :param str version: The version of Flocker to create a Homebrew recipe for.

    :returns: A Homebrew recipe for Flocker.
    """
    url = (b"https://storage.googleapis.com/archive.clusterhq.com/"
           "downloads/flocker/Flocker-{version}.tar.gz").format(
               version=version)

    dependency_graph = get_dependency_graph(u"flocker")

    return u"""require "formula"

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


def verify_recipe(recipe, version):
    """
    Revert the Yosemite VM to a state where homebrew has just been
    installed, start the machine and ssh into it. Then start a VM and test a
    Homebrew script in that VM.

    The machine must have:
        * VMWare Fusion installed,
        * A VMWare OS X VM available at a particular location

    The VM must have:
        * A snapshot with a particular name,
        * Homebrew installed and available

    :param str recipe: The contents of a Homebrew recipe to be installed.
    :param str version: The version of Flocker which the Homebrew recipe will
        install.
    """
    YOSEMITE_VMX_PATH = "{HOME}/Desktop/Virtual Machines.localized/OS X 10.10.vmwarevm/OS X 10.10.vmx".format(HOME=environ['HOME'])
    # This can likely be found another way, but I got it from within the VM:
    # System Preferences > Network
    VM_ADDRESS = "172.18.140.54"

    # XXX Requires https://github.com/msteinhoff/vmfusion-python/pull/4 to be
    # merged
    vmrun.revertToSnapshot(YOSEMITE_VMX_PATH, 'homebrew-clean')
    vmrun.start(YOSEMITE_VMX_PATH, gui=False)

    recipe_file = "flocker-{version}.rb".format(version=version)

    update = "brew update"
    install = "brew install " + recipe_file
    test = "brew test " + recipe_file

    run(username="ClusterHQVM", address=VM_ADDRESS,
        commands=[Put(content=recipe, path="~/" + recipe_file)])

    for command in [update, install, test]:
        run(username="ClusterHQVM", address=VM_ADDRESS,
            commands=[Run(command=command)])

    vmrun.stop(YOSEMITE_VMX_PATH, soft=False)


def main():
    """
    Prints a Homebrew recipe for Flocker.
    """
    version = get_version()
    recipe = create_recipe(version)
    verify_recipe(recipe=recipe, version=version)
    print recipe

if __name__ == "__main__":
    main()
