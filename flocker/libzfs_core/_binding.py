# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
CFFI-based bindings to <libzfs_core.h>.
"""

from __future__ import absolute_import

from cffi import FFI

class LibZFSCore(object):
    """
    ``LibZFSCore`` uses ``cffi`` to expose the libzfs_core C API as a Python
    API.  It presents the API as faithfully as possible.  The primary deviation
    is in the use of native Python types where they are equivalent to the C
    type used by the libzfs_core C API (rather than exposing FFI-based versions
    of those types).
    """
    def __init__(self):
        self._ffi = FFI()
        self._ffi.cdef("""
typedef struct {
    ...;
}  dmu_objset_type_t;

typedef struct {
    ...;
} nvlist_t;

int lzc_create(const char *, dmu_objset_type_t, nvlist_t *);
""")
        self._ffi.verify(
            source="""
#include <libzfs_core.h>
""",
            extra_compile_args=["-I", "/usr/include/libzfs", "-I", "/usr/include/libspl", "-D", "HAVE_IOCTL_IN_SYS_IOCTL_H"],
            libraries=["zfs_core"],
        )

    @classmethod
    def build(cls):
        lib = cls()
        return lib._ffi, lib


    def lzc_create(self, fsname, type, props):
        """
        """
        return self._ffi.lzc_create(fsname, type, props)
