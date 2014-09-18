# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Exception definitions for ``libzfs_core``.
"""

from __future__ import absolute_import

from os import strerror

class ZFSError(Exception):
    """
    An error was reported by an ``lzc_*`` API.
    """
    def __init__(self, context, errno):
        self.context = context
        self.errno = errno
        self.message = strerror(errno)
        Exception.__init__(self, self.context, self.message, self.errno)
