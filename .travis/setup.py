# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
A package of Python scripts for use in Travis-CI builds.
"""
from setuptools import setup, find_packages
setup(
    name="flocker_travis",
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'flocker-travis-script = flocker_travis.script:main',
            'flocker-travis-after-script = flocker_travis.after_script:main',
        ],
    },
)
