# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Functional tests for IPC."""

import subprocess
import os
import pwd
from unittest import skipIf

from twisted.trial.unittest import TestCase
from twisted.python.filepath import FilePath
from twisted.internet import reactor
from twisted.cred.portal import Portal
from twisted.conch.ssh.keys import Key
from twisted.conch.unix import UnixSSHRealm
from twisted.conch.checkers import SSHPublicKeyDatabase
from twisted.conch.openssh_compat.factory import OpenSSHFactory
from twisted.internet.threads import deferToThread

from .._ipc import ProcessNode
from ..test.test_ipc import make_inode_tests


_if_root = skipIf(os.getuid() != 0, "Must run as root.")


def make_cat_processnode(test_case):
    """Create a ``ProcessNode`` that just runs ``cat``.

    :return: ``ProcessNode`` that runs ``cat``.
    """
    return ProcessNode(initial_command_arguments=[b"echo"])


class ProcessINodeTests(make_inode_tests(make_cat_processnode)):
    """``INode`` tests for ``ProcessNode``."""


class ProcessNodeTests(TestCase):
    """Tests for ``ProcessNode``."""

    def test_runs_command(self):
        """``ProcessNode.run`` runs a command that is a combination of the
        initial arguments and the ones given to ``run()``."""
        node = ProcessNode(initial_command_arguments=[b"sh"])
        temp_file = self.mktemp()
        with node.run([b"-c", b"echo -n hello > " + temp_file]):
            pass
        self.assertEqual(FilePath(temp_file).getContent(), b"hello")

    def test_stdin(self):
        """``ProcessNode.run()`` context manager returns the subprocess' stdin.
        """
        node = ProcessNode(initial_command_arguments=[b"sh", b"-c"])
        temp_file = self.mktemp()
        with node.run([b"cat > " + temp_file]) as stdin:
            stdin.write(b"hello ")
            stdin.write(b"world")
        self.assertEqual(FilePath(temp_file).getContent(), b"hello world")

    def test_bad_exit(self):
        """``run()`` raises ``IOError`` if subprocess has non-zero exit code."""
        node = ProcessNode(initial_command_arguments=[])
        nonexistent = self.mktemp()
        try:
            with node.run([b"ls", nonexistent]):
                pass
        except IOError:
            pass
        else:
            self.fail("No IOError")


class InMemoryPublicKeyChecker(SSHPublicKeyDatabase):
    """Check SSH public keys in-memory."""

    def __init__(self, public_key):
        """
        :param bytes public_key: The public key we will accept.
        """
        self._key = Key.fromString(data=public_key)

    def checkKey(self, credentials):
        return self._key.blob() == credentials.blob


@_if_root
def make_sshnode(test_case):
    """Create a ``ProcessNode`` that can SSH into the local machine.

    :param TestCase test_case: The test case to use.

    :return: A ``ProcessNode`` instance.
    """
    sshd_path = FilePath(test_case.mktemp())
    sshd_path.makedirs()
    subprocess.check_call(
        [b"ssh-keygen", b"-f", sshd_path.child(b"ssh_host_key").path,
         b"-N", b"", b"-q"])

    ssh_path = FilePath(test_case.mktemp())
    ssh_path.makedirs()
    subprocess.check_call(
        [b"ssh-keygen", b"-f", ssh_path.child(b"key").path,
         b"-N", b"", b"-q"])

    factory = OpenSSHFactory()
    realm = UnixSSHRealm()
    checker = InMemoryPublicKeyChecker(ssh_path.child(b"key.pub").getContent())
    factory.portal = Portal(realm, [checker])
    factory.dataRoot = sshd_path.path
    factory.moduliRoot = b"/etc/ssh"

    port = reactor.listenTCP(0, factory, interface=b"127.0.0.1")
    test_case.addCleanup(port.stopListening)

    return ProcessNode.using_ssh(b"127.0.0.1", port.getHost().port,
                                 pwd.getpwuid(os.getuid()).pw_name,
                                 ssh_path.child(b"key"))


class SSHProcessNodeTests(TestCase):
    """Tests for ``ProcessNode.with_ssh``."""

    def test_runs_command(self):
        """``run()`` on a SSH ``ProcessNode`` runs the command on the machine
        being ssh'd into."""
        node = make_sshnode(self)
        temp_file = FilePath(self.mktemp())
        def go():
            # Commands are run with a shell... but I verified separately
            # that opensshd at least DTRT with multiple arguments,
            # including quoting.
            with node.run([b"/bin/echo -n hello > "+ temp_file.path]):
                pass
            return temp_file.getContent()
        d = deferToThread(go)

        def got_data(data):
            self.assertEqual(data, b"hello")
        d.addCallback(got_data)
        return d

    def test_stdin(self):
        """``run()`` on a SSH ``ProcessNode`` writes to the remote command's
        stdin."""
        node = make_sshnode(self)
        temp_file = FilePath(self.mktemp())
        def go():
            # Commands are run with a shell... but I verified separately
            # that opensshd at least DTRT with multiple arguments,
            # including quoting.
            with node.run([b"cat > "+ temp_file.path]) as stdin:
                stdin.write(b"hello ")
                stdin.write(b"there")
            return temp_file.getContent()
        d = deferToThread(go)

        def got_data(data):
            self.assertEqual(data, b"hello there")
        d.addCallback(got_data)
        return d

