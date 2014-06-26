# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Perform necessary SSH configuration to allow nodes to communicate directly with
each other.

This code runs in the Flocker client - that is, in an administrator's
environment, such as a laptop or desktop, not on Flocker nodes themselves.
"""

from characteristic import attributes

@attributes(["flocker_path"])
class _OpenSSHConfiguration(object):
    """
    ``OpenSSHConfiguration`` knows how to generate authentication
    configurations for OpenSSH.
    """
    @classmethod
    def defaults(cls):
        return _OpenSSHConfiguration(flocker_path=b"/etc/flocker")

    def configure_ssh(self, host, port):
        """
        Configure a node to be able to connect to other similarly configured
        Flocker nodes.

        This will block until the operation is complete.

        :param bytes host: The hostname or IP address of the node to configure.

        :param int port: The port number of the SSH server on that node.
        """
        raise Exception("Poots")


configure_ssh = _OpenSSHConfiguration.defaults().configure_ssh
