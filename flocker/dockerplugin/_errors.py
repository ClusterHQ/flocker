# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Exception types that might be raised by dockerplugin APIs
"""


class SizeOptNotExceptable(Exception):
    """
    Size that was passed in is not a good size.
    """


class UnitNotExceptable(Exception):
    """
    Size that was passed in that does not have correct unit
    """


class NoSizeExpressionFound(Exception):
    """
    No Size Expression Found
    """
