# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Testing tools related to iptables.
"""

from subprocess import check_output, check_call
from nomenclature.syscalls import unshare, setns, CLONE_NEWNET
from ipaddr import IPAddress


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
        if (
            # Comments don't matter.  They always differ because they
            # include timestamps.
            not rule.startswith("#") and
            # Chain data could matter but doesn't.  The implementation
            # doesn't mess with this stuff.  It typically differs in
            # uninteresting ways - such as matched packet counters.
            not rule.startswith(":")
        )
    ]


class _Namespace(object):
    """
    Implementation helper for :py:func:`create_network_namespace`.

    :ivar ADDRESSES: List of :py:class:`IPAddress`es in the created namespace.
    """
    # https://clusterhq.atlassian.net/browse/FLOC-135
    # Don't hardcode addresses in the created namespace
    ADDRESSES = [IPAddress('127.0.0.1'), IPAddress('10.0.0.1')]

    def create(self):
        """
        Create a new network namespace, and populate it with some addresses.
        """
        self.fd = open('/proc/self/ns/net')
        unshare(CLONE_NEWNET)
        check_call(['ip', 'link', 'set', 'up', 'lo'])
        check_call(['ip', 'link', 'add', 'eth0', 'type', 'dummy'])
        check_call(['ip', 'link', 'set', 'eth0', 'up'])
        check_call(['ip', 'addr', 'add', '10.0.0.1/8', 'dev', 'eth0'])

    def restore(self):
        """
        Restore the original network namespace.
        """
        setns(self.fd.fileno(), CLONE_NEWNET)
        self.fd.close()


def create_network_namespace():
    """
    :py:func:`create_network_namespace` is a fixture which creates a new
    network namespace, and restores the original one later.  Use the
    :py:meth:`restore`: method of the returned object to restore the orginal
    namespace.
    """
    namespace = _Namespace()
    namespace.create()
    return namespace
