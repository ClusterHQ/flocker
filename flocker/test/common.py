# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Generally helpful testing tools.
"""

__all__ = ["ArbitraryException"]



class ArbitraryException(Exception):
    """
    An exception with distinct identity and no semantic value, useful at least
    to unit tests which verify proper error logging.
    """
