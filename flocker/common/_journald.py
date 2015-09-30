"""
Minimal journald logging support.

Eventually should be moved into eliot with more extensive functionality:
https://github.com/ClusterHQ/eliot/issues/207
"""

from os import strerror

from cffi import FFI

_ffi = FFI()
_ffi.cdef("""
int sd_journal_send(const char *format, ...);
""")
_journald = _ffi.dlopen("libsystemd-journal.so.0")


def sd_journal_send(**kwargs):
    """
    Send a message to the journald log.

    @param kwargs: Mapping between field names to values, both as bytes.

    @raise IOError: If the operation failed.
    """
    # The function uses printf formatting, so we need to quote
    # percentages.
    fields = [_ffi.new("char[]", b"%s=%s" % (key, value.replace(b"%", b"%%")))
              for key, value in kwargs.items()]
    fields.append(_ffi.NULL)
    result = _journald.sd_journal_send(*fields)
    if result != 0:
        raise IOError(-result, strerror(-result))
