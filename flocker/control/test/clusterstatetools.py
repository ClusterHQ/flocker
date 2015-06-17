# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Helpers for testing ``flocker.control._clusterstate`` interactions.
"""

from .._clusterstate import EXPIRATION_TIME


def advance_some(clock):
    """
    Move the clock forward by a little time.  Much less than
    ``EXPIRATION_TIME``.
    """
    clock.advance(1)


def advance_rest(clock):
    """
    Move the clock forward by a lot of time.  Enough to reach
    ``EXPIRATION_TIME`` if ``advance_some`` is also used.
    """
    clock.advance(EXPIRATION_TIME.total_seconds() - 1)
