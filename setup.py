# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
#
# Generate a Flocker package that can be deployed onto cluster nodes.
#

from setuptools import setup, find_packages

import versioneer
versioneer.vcs = "git"
versioneer.versionfile_source = "flocker/_version.py"
versioneer.versionfile_build = "flocker/_version.py"
versioneer.tag_prefix = ""
versioneer.parentdir_prefix = "flocker-"

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
        # Pinning this isn't great in general, but we're only using UTC so meh:
        "pytz == 2014.2",
        "characteristic == 0.1.0",
        "Twisted == 13.2.0",

        "netifaces == 0.8",
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

    # Let versioneer hook into the various distutils commands so it can rewrite
    # certain data at appropriate times.
    cmdclass=versioneer.get_cmdclass(),
    )
