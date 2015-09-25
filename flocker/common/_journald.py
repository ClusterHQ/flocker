"""
Minimal journald logging support.

Eventually should be moved into eliot with more extensive functionality:
https://github.com/ClusterHQ/eliot/issues/207
"""

from cffi import FFI

_ffi = FFI()
_ffi.cdef("""
int sd_journal_send(const char *format, ...);
""")
_journald = _ffi.dlopen("libsystemd-journal.so.0")


def sd_journal_send(message):
    """
    Send a message to the journald log.

    :param bytes message: Some bytes to log.
    """
    # The function uses printf formatting, so we need to quote
    # percentages.
    _journald.sd_journal_send(b"MESSAGE=" + message.replace(b"%", b"%%"),
                              _ffi.NULL)
