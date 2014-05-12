# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
#
# Generate a Flocker package that can be deployed onto cluster nodes.
#

from setuptools import setup

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

    # This defines *Python* packages (in other words, things that can be
    # imported) which are part of the package.  Most of what they contain will
    # be included in the package automatically by virtue of the packages being
    # mentioned here.  These aren't recursive so each sub-package must also be
    # explicitly included.
    packages=[
        "flocker", "flocker.test",
        ],

    install_requires=[
        "Twisted == 13.2.0"
        ],

    extras_require={
        # This extra allows you to build the documentation for Flocker.
        "doc": ["Sphinx==1.2", "sphinx-rtd-theme==0.1.6"],
        # This extra is for developers who need to work on Flocker itself.
        "dev": ["pyflakes==0.8.1", "versioneer==0.10"]
        },

    # Let versioneer hook into the various distutils commands so it can rewrite
    # certain data at appropriate times.
    cmdclass=versioneer.get_cmdclass(),
    )
