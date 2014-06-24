# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
#
# Generate a Flocker package that can be deployed onto cluster nodes.
#

import os
from setuptools import setup, find_packages

import versioneer
versioneer.vcs = "git"
versioneer.versionfile_source = "flocker/_version.py"
versioneer.versionfile_build = "flocker/_version.py"
versioneer.tag_prefix = ""
versioneer.parentdir_prefix = "flocker-"

from distutils.core import Command
class cmd_generate_spec(Command):
    description = "Generate flocker.spec with current version."
    user_options = []
    boolean_options = []
    def initialize_options(self):
        pass
    def finalize_options(self):
        pass
    def run(self):
        with open('flocker.spec.in', 'r') as source:
            spec = source.read()
        version = "%%global flocker_version %s\n" % (versioneer.get_version(),)
        with open('flocker.spec', 'w') as destination:
            destination.write(version)
            destination.write(spec)


cmdclass = {'generate_spec': cmd_generate_spec}
# Let versioneer hook into the various distutils commands so it can rewrite
# certain data at appropriate times.
cmdclass.update(versioneer.get_cmdclass())

# Hard linking doesn't work inside Vagrant shared folders. This means that
# you can't use tox in a directory that is being shared with Vagrant,
# since tox relies on `python setup.py sdist` which uses hard links. As a
# workaround, disable hard-linking if it looks like we're a vagrant user.
# See
# https://stackoverflow.com/questions/7719380/python-setup-py-sdist-error-operation-not-permitted
# for more details.
if os.environ.get('USER','') == 'vagrant':
    del os.link

setup(
    # This is the human-targetted name of the software being packaged.
    name="Flocker",
    # This is a string giving the version of the software being packaged.  For
    # simplicity it should be something boring like X.Y.Z.
    version=versioneer.get_version(),
    # This identifies the creators of this software.  This is left symbolic for
    # ease of maintenance.
    author="HybridCluster Team",
    # This is contact information for the authors.
    author_email="support@hybridcluster.com",
    # Here is a website where more information about the software is available.
    url="http://hybridcluster.com/",

    # A short identifier for the license under which the project is released.
    license="Apache License, Version 2.0",

    # This setuptools helper will find everything that looks like a *Python*
    # package (in other words, things that can be imported) which are part of
    # the Flocker package.
    packages=find_packages(),

    entry_points = {
        # Command-line programs we want setuptools to install:
        'console_scripts': [
            'flocker-volume = flocker.volume.script:flocker_volume_main',
        ],
    },

    install_requires=[
        "eliot == 0.4.0",
        "zope.interface == 4.0.5",
        "pytz",
        "characteristic == 0.1.0",
        "Twisted == 14.0.0",

        "treq == 0.2.1",

        "netifaces >= 0.8",
        "ipaddr == 2.1.10",
        ],

    extras_require={
        # This extra allows you to build the documentation for Flocker.
        "doc": ["Sphinx==1.2", "sphinx-rtd-theme==0.1.6"],
        # This extra is for developers who need to work on Flocker itself.
        "dev": [
            # pyflakes is pretty critical to have around to help point out
            # obvious mistakes.
            "pyflakes==0.8.1",

            # Run the test suite:
            "tox==1.7.1",

            # versioneer is necessary in order to update (but *not* merely to
            # use) the automatic versioning tools.
            "versioneer==0.10",
            ]
        },

    cmdclass=cmdclass,

    # Some "trove classifiers" which are relevant.
    classifiers=[
        "License :: OSI Approved :: Apache Software License",
        ],
    )
