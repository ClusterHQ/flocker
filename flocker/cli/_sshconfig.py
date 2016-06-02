# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Perform necessary SSH configuration to allow nodes to communicate directly with
each other.

This code runs in the Flocker client - that is, in an administrator's
environment, such as a laptop or desktop, not on Flocker nodes themselves (it
may accidentally work on the Flocker nodes but this is not the expected use).
"""

from os import devnull
from os.path import expanduser
from subprocess import check_call, check_output, STDOUT

from characteristic import attributes

from ipaddr import IPv4Address

from twisted.python.filepath import FilePath


def ssh(argv):
    # We capture stderr so that if there is a failure we will raise
    # exception that includes both stdout and stderr. This can then be
    # shown to the user for diagnostic purposes.
    # See https://clusterhq.atlassian.net/browse/FLOC-192 for potentially
    # better error handling.
    check_output([b"ssh"] + argv, stderr=STDOUT)


DEFAULT_SSH_DIRECTORY = FilePath(expanduser(b"~/.ssh/"))


@attributes(["flocker_path", "ssh_config_path"])
class OpenSSHConfiguration(object):
    """
    ``OpenSSHConfiguration`` knows how to generate authentication
    configurations for OpenSSH.

    :ivar FilePath flocker_path: The path to the directory which holds
        Flocker-related configuration.  For example, ``/etc/flocker``.  This is
        a path used on Flocker nodes (not on the client).

    :ivar ssh_config_path: The path to the directory which holds SSH-related
        configuration.  For example, ``~/.ssh/``.  This is a path used on the
        client node.
    """
    @classmethod
    def defaults(cls):
        """
        Create an ``OpenSSHConfiguration`` configured with the standard paths
        for Flocker and OpenSSH.
        """
        return OpenSSHConfiguration(
            flocker_path=FilePath(b"/etc/flocker"),
            ssh_config_path=DEFAULT_SSH_DIRECTORY)

    def create_keypair(self):
        """
        Create a key pair for communicating with remote nodes and which will
        be transferred to the remote nodes so that they can communicate with
        each other.

        This will block until the operation is complete.
        """
        local_private_path = self.ssh_config_path.child(b"id_rsa_flocker")

        if not self.ssh_config_path.isdir():
            self.ssh_config_path.makedirs()

        if not local_private_path.exists():
            with open(devnull, "w") as discard:
                # See https://clusterhq.atlassian.net/browse/FLOC-192
                check_call(
                    [b"ssh-keygen", b"-N", b"", b"-f",
                     local_private_path.path],
                    stdout=discard, stderr=discard
                )

    def configure_ssh(self, host, port):
        """
        Configure a node to be able to connect to other similarly configured
        Flocker nodes.

        This will block until the operation is complete.

        :param bytes host: The hostname or IP address of the node to configure.

        :param int port: The port number of the SSH server on that node.
        """
        if isinstance(host, IPv4Address):
            host = unicode(host).encode("ascii")
        local_private_path = self.ssh_config_path.child(b"id_rsa_flocker")
        local_public_path = local_private_path.siblingExtension(b".pub")

        remote_private_path = self.flocker_path.child(b"id_rsa_flocker")
        remote_public_path = remote_private_path.siblingExtension(b".pub")

        write_authorized_key = (
            u"mkdir -p .ssh; "
            u"if ! grep --quiet '{public_key}' .ssh/authorized_keys; then"
            u"  ("
            u"    echo; "
            u"    echo '# flocker-deploy access'; "
            u"    echo '{public_key}'; "
            u"  ) >> .ssh/authorized_keys; "
            u"fi; ".format(
                public_key=local_public_path.getContent().strip())
            )

        generate_flocker_key = (
            u"umask u=rwx,g=,o=; "
            u"mkdir -p {}; "
            u"echo '{}' > '{}'; "
            u"echo '{}' > '{}'; "
            u"chmod u=rw,g=,o= {}; "
            u"chmod u=rw,g=r,o=r {}".format(
                remote_public_path.parent().path,
                local_public_path.getContent().strip(),
                remote_public_path.path,
                local_private_path.getContent().strip(),
                remote_private_path.path,
                remote_private_path.path,
                remote_public_path.path,)
            )

        commands = write_authorized_key + generate_flocker_key

        ssh([u"-oPort={}".format(port).encode("ascii"),
             # We're ok with unknown hosts; we'll be switching away from SSH by
             # the time Flocker is production-ready and security is a concern.
             b"-oStrictHostKeyChecking=no",
             # Some systems (notably Ubuntu) enable GSSAPI authentication which
             # involves a slow DNS operation before failing and moving on to a
             # working mechanism.  The expectation is that key-based auth will
             # be in use so just jump straight to that.  An alternate solution,
             # explicitly disabling GSSAPI, has cross-version platform and
             # cross-version difficulties (the options aren't always recognized
             # and result in an immediate failure).  As mentioned above, we'll
             # switch away from SSH soon.
             b"-o", b"PreferredAuthentications=publickey",
             # The tests hang if ControlMaster is set, since OpenSSH won't
             # ever close the connection to the test server.
             b"-oControlMaster=no",
             # Connect as root, since we need superuser permissions for
             # ZFS and Docker:
             b"-l", b"root",
             host, commands.encode("ascii")])

configure_ssh = OpenSSHConfiguration.defaults().configure_ssh
