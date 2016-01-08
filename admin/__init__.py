# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Admin scripts and modules which should not be shipped with Flocker.

Since :module:`admin.release` is imported from setup.py, we need to ensure that
this only imports things from the stdlib.
"""
