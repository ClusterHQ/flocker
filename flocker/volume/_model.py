# Copyright ClusterHQ Inc.  See LICENSE file for details.
# -*- test-case-name: flocker.volume.test.test_service -*-

"""
Record types for representing volume models.
"""

from characteristic import attributes


@attributes(["maximum_size"], apply_immutable=True)
class VolumeSize(object):
    """
    A data volume's size.

    :ivar int maximum_size: The upper bound on the amount of data that can be
        stored on this volume, in bytes.  May also be ``None`` to indicate no
        particular upper bound is required (when representing desired
        configuration) or known (when representing deployed configuration).
    """
