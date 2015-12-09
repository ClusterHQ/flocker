# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
Inserts flocker on to sys.path.

This module should only be imported by scripts living in :file:`admin`, as the
first thing they do.

:var FilePath TOPLEVEL: The top-level of the flocker repository.
:var FilePath BASEPATH: The executable being run.
"""

from twisted.python.filepath import FilePath
import sys

path = BASEPATH = FilePath(sys.argv[0])
for parent in path.parents():
    if parent.descendant(['flocker', '__init__.py']).exists():
        TOPLEVEL = parent
        sys.path.insert(0, parent.path)
        break
else:
    raise ImportError("Could not find top-level.")

__all__ = ['TOPLEVEL', 'BASEPATH']
