# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
A library exposing libzfs_core, the ZFS C API, to Python using CFFI.
"""

from __future__ import absolute_import

from ._binding import LibZFSCore
from ._error import ZFSError

(ffi, lib) = LibZFSCore.build()

__all__ = [
    "ZFSError",

    "ffi", "lib",
    ]
