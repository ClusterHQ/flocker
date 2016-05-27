# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Generate a Flocker package that can be deployed onto cluster nodes.
"""

import pkg_resources
from setuptools import setup, find_packages
import versioneer

with open("README.rst") as readme:
    description = readme.read()


def parse_requirements(requirements_file, dependency_links):
    """
    Parse a requirements file.

    Requirements that have an environment marker will only be included
    in the list if the marker evaluates True.

    ``--find-links`` lines will be added to the supplied ``dependency_links``
    list.

    XXX There's a package called ``pbr`` which is also supposed to do this
    job. I couldn't get it to work --RichardW.
    """
    requirements = []
    with open(requirements_file) as f:
        for line in f:
            line = line.rstrip()
            if line.startswith('#'):
                continue
            elif line.startswith('--find-links'):
                link = line.split(None, 1)[1]
                dependency_links.append(link)
            else:
                (req,) = list(pkg_resources.parse_requirements(line))
                if getattr(req, "marker", None) and not req.marker.evaluate():
                    continue
                requirements.append(unicode(req))
    return requirements

# Parse the ``.in`` files. This will allow the dependencies to float when
# Flocker is installed using ``pip install .``.
# It also allows Flocker to be imported as a package alongside other Python
# libraries that may require different versions than those specified in
# Flocker's pinned dependency files.
dependency_links = []
install_requires = parse_requirements(
    "requirements/flocker.txt.in",
    dependency_links,
)
dev_requires = parse_requirements(
    "requirements/flocker-dev.txt.in",
    dependency_links,
)

setup(
    # This is the human-targetted name of the software being packaged.
    name="Flocker",
    # This is a string giving the version of the software being packaged.  For
    # simplicity it should be something boring like X.Y.Z.
    version=versioneer.get_version(),
    # This identifies the creators of this software.  This is left symbolic for
    # ease of maintenance.
    author="ClusterHQ Team",
    # This is contact information for the authors.
    author_email="support@clusterhq.com",
    # Here is a website where more information about the software is available.
    url="https://clusterhq.com/",

    # A short identifier for the license under which the project is released.
    license="Apache License, Version 2.0",

    # Some details about what Flocker is.  Synchronized with the README.rst to
    # keep it up to date more easily.
    long_description=description,

    # This setuptools helper will find everything that looks like a *Python*
    # package (in other words, things that can be imported) which are part of
    # the Flocker package.
    packages=find_packages(exclude=('admin', 'admin.*')),

    package_data={
        'flocker.node.functional': [
            'sendbytes-docker/*',
            'env-docker/*',
            'retry-docker/*'
        ],
        # These data files are used by the volumes API to define input and
        # output schemas.
        'flocker.control': ['schema/*.yml'],
        # These files are used by the Docker plugin API:
        'flocker.dockerplugin': ['schema/*.yml'],
        # Configuration schema, used to detect need for upgrade code:
        'flocker.control.test': [
            'persisted_model.json', 'configurations/*.json'
        ],
    },

    entry_points={
        # These are the command-line programs we want setuptools to install.
        # Don't forget to modify the omnibus packaging tool
        # (admin/packaging.py) if you make changes here.
        'console_scripts': [
            'flocker-volume = flocker.volume.script:flocker_volume_main',
            'flocker-deploy = flocker.cli.script:flocker_deploy_main',
            'flocker-container-agent = flocker.node.script:flocker_container_agent_main',  # noqa
            'flocker-dataset-agent = flocker.node.script:flocker_dataset_agent_main',  # noqa
            'flocker-control = flocker.control.script:flocker_control_main',
            'flocker-ca = flocker.ca._script:flocker_ca_main',
            'flocker = flocker.cli.script:flocker_cli_main',
            'flocker-docker-plugin = ' +
            'flocker.dockerplugin._script:docker_plugin_main',
            'flocker-diagnostics = ' +
            'flocker.node.script:flocker_diagnostics_main',
            'flocker-benchmark = ' +
            'flocker.node.benchmark:flocker_benchmark_main',
            'flocker-node-era = flocker.common._era:era_main',
        ],
    },

    install_requires=install_requires,

    extras_require={
        # This extra is for developers who need to work on Flocker itself.
        "dev": dev_requires,
    },

    cmdclass=versioneer.get_cmdclass(),

    # Duplicate dependency links may have been added from different
    # requirements files.
    dependency_links=list(set(dependency_links)),

    # Some "trove classifiers" which are relevant.
    classifiers=[
        "License :: OSI Approved :: Apache Software License",
        ],
    )
