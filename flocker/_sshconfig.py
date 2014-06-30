# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Perform necessary SSH configuration to allow nodes to communicate directly with
each other.

This code runs in the Flocker client - that is, in an administrator's
environment, such as a laptop or desktop, not on Flocker nodes themselves.
"""

from os import devnull
from os.path import expanduser
from subprocess import check_call

from characteristic import attributes

from twisted.python.filepath import FilePath

@attributes(["flocker_path", "ssh_config_path"])
class _OpenSSHConfiguration(object):
    """
    ``OpenSSHConfiguration`` knows how to generate authentication
    configurations for OpenSSH.
    """
    @classmethod
    def defaults(cls):
        return _OpenSSHConfiguration(
            flocker_path=FilePath(b"/etc/flocker"),
            ssh_config_path=FilePath(expanduser(b"~/.ssh/")))

    def configure_ssh(self, host, port):
        """
        Configure a node to be able to connect to other similarly configured
        Flocker nodes.

        This will block until the operation is complete.

        :param bytes host: The hostname or IP address of the node to configure.

        :param int port: The port number of the SSH server on that node.
        """
        if not self.ssh_config_path.isdir():
            self.ssh_config_path.makedirs()
        key = self.ssh_config_path.child(b"id_rsa_flocker")
        if not key.exists():
            with open(devnull) as discard:
                check_call(
                    [b"ssh-keygen", b"-N", b"", b"-f", key.path],
                    stdout=discard, stderr=discard
                )

configure_ssh = _OpenSSHConfiguration.defaults().configure_ssh
