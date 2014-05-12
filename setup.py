# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
#
# Generate a Flocker package that can be deployed onto cluster nodes.
#

import os.path

from setuptools import setup

path = os.path.join(os.path.dirname(__file__), b"flocker/version")
with open(path) as fObj:
    version = fObj.read().strip()
del path

setup(
    # This is the human-targetted name of the software being packaged.
    name="Flocker",
    # This is a string giving the version of the software being packaged.  For
    # simplicity it should be something boring like X.Y.Z.
    version=version,
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

    # This defines extra non-source files that live in the source tree that
    # need to be included as part of the package.
    package_data={
        # This is the canonical definition of the source form of the cluster
        # version.
        "flocker": ["version"],
        },

    install_requires=[
        "machinist == 0.1",
        "zope.interface == 4.0.5",
        # Pinning this isn't great in general, but we're only using UTC so meh:
        "pytz == 2014.2",
        "Twisted == 13.2.0"
        ],

    extras_require={
        # This extra allows you to build the documentation for Flocker.
        "doc": ["Sphinx==1.2", "sphinx-rtd-theme==0.1.6"],
        # This extra is for developers who need to work on Flocker itself.
        "dev": ["pyflakes==0.8.1"]
        },
    )
