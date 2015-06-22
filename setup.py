# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Generate a Flocker package that can be deployed onto cluster nodes.
"""

import os
import platform
from setuptools import setup, find_packages

import versioneer
versioneer.vcs = "git"
versioneer.versionfile_source = "flocker/_version.py"
versioneer.versionfile_build = "flocker/_version.py"
versioneer.tag_prefix = ""
versioneer.parentdir_prefix = "flocker-"

cmdclass = {}

# Let versioneer hook into the various distutils commands so it can rewrite
# certain data at appropriate times.
cmdclass.update(versioneer.get_cmdclass())

# Hard linking doesn't work inside VirtualBox shared folders. This means that
# you can't use tox in a directory that is being shared with Vagrant,
# since tox relies on `python setup.py sdist` which uses hard links. As a
# workaround, disable hard-linking if setup.py is a descendant of /vagrant.
# See
# https://stackoverflow.com/questions/7719380/python-setup-py-sdist-error-operation-not-permitted
# for more details.
if os.path.abspath(__file__).split(os.path.sep)[1] == 'vagrant':
    del os.link

with open("README.rst") as readme:
    description = readme.read()

dev_requirements = [
    # flake8 is pretty critical to have around to help point out
    # obvious mistakes. It depends on PEP8, pyflakes and mccabe.
    "pyflakes==0.8.1",
    "pep8==1.5.7",
    "mccabe==0.2.1",
    "flake8==2.2.0",

    # Run the test suite:
    "tox==1.7.1",

    # versioneer is necessary in order to update (but *not* merely to
    # use) the automatic versioning tools.
    "versioneer==0.10",

    # Some of the tests use Conch:
    "PyCrypto==2.6.1",
    "pyasn1==0.1.8",

    # The acceptance tests interact with MongoDB
    "pymongo>=2.7.2",

    # The acceptance tests interact with PostgreSQL
    "pg8000==1.10.1",

    # The acceptance tests interact with MySQL
    "PyMySQL==0.6.2",

    # The acceptance tests interact with Kibana via WebKit
    "selenium==2.44.0",

    # The cloud acceptance test runner needs these
    "fabric==1.10.0",
    "apache-libcloud==0.16.0",

    # Packages are downloaded from Buildbot
    "requests==2.4.3",
    "requests-file==1.0",

    "wheel==0.24.0",
    "gitpython==1.0.0",
    "tl.eggdeps==0.4",
    "boto==2.30.0",
]

install_requirements = [
    # This is necessary for a release because our version scheme does not
    # adhere to PEP440.
    # See https://clusterhq.atlassian.net/browse/FLOC-1373
    "setuptools==3.6",
    "eliot == 0.7.1",
    "machinist == 0.2.0",
    "zope.interface >= 4.0.5",
    "pytz",
    "characteristic >= 14.1.0",
    "Twisted == 15.1.0",
    # TLS support libraries for Twisted:
    "service_identity == 14.0.0",
    "idna == 2.0",
    "pyOpenSSL == 0.15.1",

    "PyYAML == 3.10",

    "treq == 0.2.1",

    "psutil == 2.1.2",
    "netifaces >= 0.8",
    "ipaddr == 2.1.11",
    "docker-py == 0.7.1",
    "jsonschema == 2.4.0",
    "klein == 0.2.3",
    "pyrsistent == 0.9.2",
    "pycrypto == 2.6.1",
    "effect==0.1a13",
    "bitmath==1.2.3-4",
    "boto==2.38.0",
]

# The test suite uses network namespaces
# nomenclature can only be installed on Linux
if platform.system() == 'Linux':
    dev_requirements.extend([
        "nomenclature >= 0.1.0",
    ])
    install_requirements.extend([
        "python-cinderclient==1.1.1",
        "python-novaclient==2.24.1",
        "python-keystoneclient==1.4.0",
        "python-keystoneclient-rackspace==0.1.3",
    ])

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
        ],
    },

    install_requires=install_requirements,    extras_require={
        # This extra allows you to build and check the documentation for
        # Flocker.
        "doc": [
            "Sphinx==1.2.2",
            "sphinx-rtd-theme==0.1.6",
            "pyenchant==1.6.6",
            "sphinxcontrib-spelling==2.1.1",
            "sphinx-prompt==1.0.0",
            "sphinxcontrib-httpdomain==1.3.0",
            ],
        # This extra is for developers who need to work on Flocker itself.
        "dev": dev_requirements,

        # This extra is for Flocker release engineers to set up their release
        # environment.
        "release": [
            "gitpython==1.0.0",
            "awscli==1.7.25",
            "wheel==0.24.0",
            "virtualenv",
            "PyCrypto",
            "pyasn1",
            "tl.eggdeps==0.4",
            "boto==2.38.0",
            # Packages are downloaded from Buildbot
            "requests==2.4.3",
            "requests-file==1.0",
            # TLS SNI Support is needed to test link redirects
            "ndg-httpsclient==0.4.0",
            ],
        },

    cmdclass=cmdclass,

    # Some "trove classifiers" which are relevant.
    classifiers=[
        "License :: OSI Approved :: Apache Software License",
        ],
    )
