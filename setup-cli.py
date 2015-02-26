# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Generate a Flocker package that can be deployed onto cluster nodes.
"""

import os
from setuptools import setup, find_packages

import versioneer
versioneer.vcs = "git"
versioneer.versionfile_source = "flocker_cli/_version.py"
versioneer.versionfile_build = "flocker_cli/_version.py"
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

setup(
    # This is the human-targetted name of the software being packaged.
    name="Flocker CLI",
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
    },

    entry_points = {
        # These are the command-line programs we want setuptools to install.
        # Don't forget to modify the omnibus packaging tool
        # (admin/packaging.py) if you make changes here.
        'console_scripts': [
            'flocker = flocker_cli.script:flocker_cli_main',
        ],
    },

    install_requires=[
        "setuptools >= 1.4, < 8.0",  # < 8.0 to avoid PEP440 warnings

        "eliot",
        "zope.interface >= 4.0.5",
        "characteristic >= 14.1.0",
        "Twisted == 15.0.0",
        "PyYAML == 3.10",
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
            "effect==0.1a13",
            "boto==2.30.0",
            ],
        },

    cmdclass=cmdclass,

    # Some "trove classifiers" which are relevant.
    classifiers=[
        "License :: OSI Approved :: Apache Software License",
        ],
    )
