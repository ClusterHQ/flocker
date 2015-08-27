# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Flocker is a hypervisor that provides ZFS-based replication and fail-over
functionality to a Linux-based user-space operating system.
"""


def _disable_pyrsistent_c_extensions():
    """
    Pyrsistent sometimes segfaults. Disabling C extensions reduces the
    likelihood of this happening.

    We do this first so it happens before pyrsistent is imported.

    See https://github.com/tobgu/pyrsistent/issues/52 and FLOC-2913.

    The mechanism for disabling extensions is documented at
    https://github.com/tobgu/pyrsistent/blob/master/CHANGES.txt#L17-L19.
    """
    import os
    os.environ[b"PYRSISTENT_NO_C_EXTENSION"] = b"1"
_disable_pyrsistent_c_extensions()
del _disable_pyrsistent_c_extensions


def _suppress_warnings():
    """
    Suppress warnings when not running under trial.
    """
    import warnings
    import sys
    import os
    if os.path.basename(sys.argv[0]) != "trial":
        warnings.simplefilter("ignore")
_suppress_warnings()
del _suppress_warnings


from ._version import get_versions
__version__ = get_versions()['version']
del get_versions


def _redirect_eliot_logs_for_trial():
    """
    Enable Eliot logging to the ``_trial/test.log`` file.

    This wrapper function allows flocker/__version__.py to be imported by
    packaging tools without them having to install all the Flocker Eliot
    dependencies. E.g in ``Flocker/admin/vagrant.py``.
    """
    import os
    import sys
    if os.path.basename(sys.argv[0]) == "trial":
        from eliot.twisted import redirectLogsForTrial
        redirectLogsForTrial()
_redirect_eliot_logs_for_trial()
del _redirect_eliot_logs_for_trial
