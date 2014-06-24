# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Testing tools related to iptables.
"""

from subprocess import check_output
from nomenclature.syscalls import unshare, setns, CLONE_NEWNET


def get_iptables_rules():
    """
    Return a list of :command:`iptables-save`-formatted rule strings with
    comments and packet/byte counter lines removed.

    This also removes the information about the default policy for chains
    (which might someday be important).
    """
    rules = check_output([b"iptables-save"])
    return [
            rule
            for rule in rules.splitlines()
            # Comments don't matter.  They always differ because they
            # include timestamps.
            if not rule.startswith("#")
            # Chain data could matter but doesn't.  The implementation
            # doesn't mess with this stuff.  It typically differs in
            # uninteresting ways - such as matched packet counters.
            and not rule.startswith(":")]


class _Preserver(object):
    """
    Implementation helper for :py:func:`preserve_iptables`.
    """
    def preserve(self):
        """
        Use ``iptables-save`` to record the current rules.
        """
        self.fd = open('/proc/self/ns/net')
        unshare(CLONE_NEWNET)
        import os
        os.system('ip link set up lo')
        os.system('ip link add eth0 type dummy')
        os.system('ip link set eth0 up')
        os.system('ip addr add 10.0.0.1/8 dev eth0')


    def restore(self):
        """
        Use ``iptables-restore`` to put the previously recorded rules back on
        the system.

        :raise Exception: If the ``iptables-restore`` command exits with an
            error code.
        """
        setns(self.fd.fileno(), CLONE_NEWNET)
        self.fd.close()


def preserve_iptables():
    """
    :py:func:`preserve_iptables` is a fixture which saves the current iptables
    configuration and restores it later.  Use the :py:meth:`restore`: method of
    the returned object to restore the rules as they were at the time this
    function was called.
    """
    preserver = _Preserver()
    preserver.preserve()
    return preserver
