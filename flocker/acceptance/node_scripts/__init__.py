# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Python scripts to be run on nodes as part of tests.
"""

from twisted.python.filepath import FilePath


# Directory where scripts are stored:
SCRIPTS = FilePath(__file__).parent()


__all__ = ["SCRIPTS"]
