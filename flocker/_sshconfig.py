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


def ssh(argv):
    with open(devnull, "w") as discard:
        check_call([b"ssh"] + argv, stdout=discard, stderr=discard)


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
        local_private_path = self.ssh_config_path.child(b"id_rsa_flocker")
        local_public_path = local_private_path.siblingExtension(b".pub")

        remote_private_path = self.flocker_config_path.child(b"id_rsa_flocker")
        remote_public_path = remote_private_path.siblingExtension(b".pub")

        if not self.ssh_config_path.isdir():
            self.ssh_config_path.makedirs()

        if not local_private_path.exists():
            with open(devnull, "w") as discard:
                check_call(
                    [b"ssh-keygen", b"-N", b"", b"-f", local_private_path.path],
                    stdout=discard, stderr=discard
                )

        write_authorized_key = (
            u"("
            u"echo; "
            u"echo '# flocker-deploy access'; "
            u"echo {}) >> .ssh/authorized_keys".format(
                local_public_path.getContent())
            ).encode("ascii")

        generate_flocker_key = (
            u"echo {} > {}; echo {} > {}".format(
                local_public_path.getContent(), remote_public_path.path,
                local_private_path.getContent(), remote_private_path.path
            )).encode("ascii")

        commands = write_authorized_key + b"; " + generate_flocker_key

        ssh([b"-oPort={}".format(port), host, commands])

configure_ssh = _OpenSSHConfiguration.defaults().configure_ssh
