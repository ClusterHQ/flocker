# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
CFFI-based bindings to <libzfs_core.h>.
"""

from __future__ import absolute_import

from cffi import FFI

class _module(object):
    header = ""
    integer_constants = []
    typedef = ""
    prototype = ""


class _sys(_module):
    header = "#include <sys/fs/zfs.h>"
    integer_constants = []
    typedef = """
enum dmu_objset_type_t {
    DMU_OST_NONE,
    DMU_OST_META,
    DMU_OST_ZFS,
    DMU_OST_ZVOL,
    /* For testing only! */
    DMU_OST_OTHER,
    /* Be careful! */
    DMU_OST_ANY,
    DMU_OST_NUMTYPES
};
"""


class _nvpair(_module):
    header = ""
    typedef = """
typedef struct {
    ...;
} nvlist_t;
"""


class _lzc(_module):
    header = """
#include <libzfs_core.h>
"""
    # Not in 0.6.3
    # integer_constants = ["LZC_SEND_FLAG_EMBED_DATA"]
    typedef = ""
    prototype = """
int lzc_create(const char *, dmu_objset_type_t, nvlist_t *);
"""

def _assemble_cdef_integer_constants(names):
    return "\n".join([
        "static const int " + name + ";"
        for name in names
    ]) + "\n"


def _assemble_cdef(modules):
    assemblers = {
        "integer_constants": _assemble_cdef_integer_constants,
    }
    return "\n".join([
        assemblers.get(kind, lambda s: s)(getattr(module, kind))
        for kind in ["integer_constants", "typedef", "prototype"]
        for module in modules
    ])


class LibZFSCore(object):
    """
    ``LibZFSCore`` uses ``cffi`` to expose the libzfs_core C API as a Python
    API.  It presents the API as faithfully as possible.  The primary deviation
    is in the use of native Python types where they are equivalent to the C
    type used by the libzfs_core C API (rather than exposing FFI-based versions
    of those types).
    """
    _modules = [_sys, _nvpair, _lzc]

    def __init__(self):
        self._ffi = FFI()
        self._ffi.cdef(_assemble_cdef(self._modules))
        self._lib = self._ffi.verify(
            source="\n".join([
                module.header
                for module in self._modules
            ]),
            extra_compile_args=["-I", "/usr/include/libzfs", "-I", "/usr/include/libspl", "-D", "HAVE_IOCTL_IN_SYS_IOCTL_H"],
            libraries=["zfs_core"],
        )

        for module in self._modules:
            for name in module.integer_constants:
                setattr(self, name, getattr(self._lib, name))

    @classmethod
    def build(cls):
        lib = cls()
        return lib._ffi, lib


    def lzc_create(self, fsname, type, props):
        """
        """
        return self._lib.lzc_create(fsname, self._ffi.NULL, self._ffi.NULL)
