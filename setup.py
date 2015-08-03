# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Generate a Flocker package that can be deployed onto cluster nodes.
"""

import os
import platform
from setuptools import setup, find_packages
import versioneer

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

with open("requirements.txt") as requirements:
    install_requires = requirements.readlines()
with open("dev-requirements.txt") as dev_requirements:
    dev_requires = dev_requirements.readlines()

# The test suite uses network namespaces
# nomenclature can only be installed on Linux
if platform.system() == 'Linux':
    dev_requires.extend([
        "nomenclature >= 0.1.0",
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

    install_requires=install_requires,

    extras_require={
        # This extra is for developers who need to work on Flocker itself.
        "dev": dev_requires,
        },

    cmdclass=versioneer.get_cmdclass(),

    # Some "trove classifiers" which are relevant.
    classifiers=[
        "License :: OSI Approved :: Apache Software License",
        ],
    )
