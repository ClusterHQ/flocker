# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Exception types that might be raised by filesystem APIs.
"""


class MaximumSizeTooSmall(Exception):
    """
    A maximum size was specified for a filesystem which is smaller than the
    smallest allowed value.
    """
