# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Generate a Flocker package that can be deployed onto cluster nodes.
"""

import os
from setuptools import setup, find_packages

import versioneer
versioneer.vcs = "git"
versioneer.versionfile_source = "flocker/_version.py"
versioneer.versionfile_build = "flocker/_version.py"
versioneer.tag_prefix = ""
versioneer.parentdir_prefix = "flocker-"

from distutils.core import Command

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

    entry_points = {
        # These are the command-line programs we want setuptools to install.
        # Don't forget to modify the omnibus packaging tool
        # (admin/packaging.py) if you make changes here.
        'console_scripts': [
            'flocker-volume = flocker.volume.script:flocker_volume_main',
            'flocker-deploy = flocker.cli.script:flocker_deploy_main',
            'flocker-changestate = flocker.node.script:flocker_changestate_main',
            'flocker-reportstate = flocker.node.script:flocker_reportstate_main',
            'flocker-zfs-agent = flocker.node.script:flocker_zfs_agent_main',
            'flocker-control = flocker.control.script:flocker_control_main',
        ],
    },

    install_requires=[
        "setuptools >= 1.4",

        "eliot == 0.4.0",
        "machinist == 0.2.0",
        "zope.interface >= 4.0.5",
        "pytz",
        "characteristic >= 14.1.0",
        "Twisted == 15.0.0",

        "PyYAML == 3.10",

        "treq == 0.2.1",

        "psutil == 2.1.2",
        "netifaces >= 0.8",
        "ipaddr == 2.1.11",
        "docker-py == 0.7.1",
        "jsonschema == 2.4.0",
        "klein == 0.2.3",
        "pyrsistent == 0.7.0",
        ],

    extras_require={
        # This extra allows you to build and check the documentation for
        # Flocker.
        "doc": [
            "Sphinx==1.2.2",
            "sphinx-rtd-theme==0.1.6",
            "pyenchant==1.6.6",
            "sphinxcontrib-spelling==2.1.1",
            "sphinx-prompt==0.2.2",
            "sphinxcontrib-httpdomain==1.3.0",
            ],
        # This extra is for developers who need to work on Flocker itself.
        "dev": [
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
            "pyasn1==0.1.7",

            # The test suite uses network namespaces
            "nomenclature >= 0.1.0",

            # The acceptance tests interact with MongoDB
            "pymongo>=2.7.2",

            # The acceptance tests interact with PostgreSQL
            "pg8000==1.10.1",

            # The acceptance tests interact with MySQL
            "PyMySQL==0.6.2",

            # The acceptance tests interact with elasticsearch
            "elasticsearch==1.2.0",

            # The acceptance tests interact with Kibana via WebKit
            "selenium==2.44.0",

            # The cloud acceptance test runner needs these
            "fabric==1.10.0",
            "apache-libcloud==0.16.0",
            "digitalocean-python==0.1.5",
            ],

        # This extra is for Flocker release engineers to set up their release
        # environment.
        "release": [
            "gsutil",
            "wheel",
            "virtualenv",
            "PyCrypto",
            "pyasn1",
            "tl.eggdeps",
            ],
        },

    cmdclass=cmdclass,

    # Some "trove classifiers" which are relevant.
    classifiers=[
        "License :: OSI Approved :: Apache Software License",
        ],
    )
