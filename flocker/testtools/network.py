# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Testing tools related to iptables.
"""

from functools import wraps
from subprocess import check_call

from nomenclature.syscalls import unshare, setns, CLONE_NEWNET, CLONE_NEWNS
from ipaddr import IPAddress
from twisted.python.filepath import FilePath

from flocker.common._filepath import temporary_directory


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
        self.net_fd = open('/proc/self/ns/net')
        self.mnt_fd = open('/proc/self/ns/mnt')
        unshare(CLONE_NEWNET)
        unshare(CLONE_NEWNS)
        self.tmp = temporary_directory()
        self.hosts_file = self.tmp.child('hosts')
        self.hosts_file.touch()
        self.hosts = {}
        check_call(["mount", "--make-rslave", "/"])
        check_call(["mount", "--bind", self.hosts_file.path, "/etc/hosts"])
        check_call(['ip', 'link', 'set', 'up', 'lo'])
        check_call(['ip', 'link', 'add', 'eth0', 'type', 'dummy'])
        check_call(['ip', 'link', 'set', 'eth0', 'up'])
        check_call(['ip', 'addr', 'add', '10.0.0.1/8', 'dev', 'eth0'])

    def add_host(self, hostname):
        self.hosts[hostname] = "10.0.0.1"
        with self.hosts_file.open('w') as f:
            f.write(
                "\n".join(
                    "{} {}".format(
                        address, hostname
                    ) for hostname, address in self.hosts.items()
                )
            )

    def drop(self):
        check_call("iptables --insert OUTPUT --proto tcp --jump DROP".split())

    def restore(self):
        """
        Restore the original network namespace.
        """
        setns(self.net_fd.fileno(), CLONE_NEWNET)
        self.net_fd.close()
        setns(self.mnt_fd.fileno(), CLONE_NEWNS)
        self.mnt_fd.close()
        self.tmp.remove()


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


def with_network_simulator(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        nns = create_network_namespace()
        kwargs["network"] = nns
        try:
            return f(*args, **kwargs)
        finally:
            nns.restore()
    return wrapper
