# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Functional tests for IPC."""

import os
from getpass import getuser
from unittest import skipIf

from twisted.trial.unittest import TestCase
from twisted.python.filepath import FilePath
from twisted.internet.threads import deferToThread

from .._ipc import ProcessNode
from ..test.test_ipc import make_inode_tests
from ...testtools import create_ssh_server

_if_root = skipIf(os.getuid() != 0, "Must run as root.")


def make_echo_processnode(test_case):
    """Create a ``ProcessNode`` that just runs ``echo``.

    :return: ``ProcessNode`` that runs ``echo``.
    """
    return ProcessNode(initial_command_arguments=[b"echo"])


class ProcessINodeTests(make_inode_tests(make_echo_processnode)):
    """``INode`` tests for ``ProcessNode``."""


class ProcessNodeTests(TestCase):
    """Tests for ``ProcessNode``."""

    def test_run_runs_command(self):
        """
        ``ProcessNode.run`` runs a command that is a combination of the
        initial arguments and the ones given to ``run()``.
        """
        node = ProcessNode(initial_command_arguments=[b"sh"])
        temp_file = self.mktemp()
        with node.run([b"-c", b"echo -n hello > " + temp_file]):
            pass
        self.assertEqual(FilePath(temp_file).getContent(), b"hello")

    def test_run_stdin(self):
        """
        ``ProcessNode.run()`` context manager returns the subprocess' stdin.
        """
        node = ProcessNode(initial_command_arguments=[b"sh", b"-c"])
        temp_file = self.mktemp()
        with node.run([b"cat > " + temp_file]) as stdin:
            stdin.write(b"hello ")
            stdin.write(b"world")
        self.assertEqual(FilePath(temp_file).getContent(), b"hello world")

    def test_run_bad_exit(self):
        """
        ``run()`` raises ``IOError`` if subprocess has non-zero exit code.
        """
        node = ProcessNode(initial_command_arguments=[])
        nonexistent = self.mktemp()
        try:
            with node.run([b"ls", nonexistent]):
                pass
        except IOError:
            pass
        else:
            self.fail("No IOError")

    def test_get_output_runs_command(self):
        """
        ``ProcessNode.get_output()`` runs a command that is the combination of
        the initial arguments and the ones given to ``get_output()``.
        """
        node = ProcessNode(initial_command_arguments=[b"sh"])
        temp_file = self.mktemp()
        node.get_output([b"-c", b"echo -n hello > " + temp_file])
        self.assertEqual(FilePath(temp_file).getContent(), b"hello")

    def test_get_output_result(self):
        """
        ``get_output()`` returns the output of the command.
        """
        node = ProcessNode(initial_command_arguments=[])
        result = node.get_output([b"echo", b"-n", b"hello"])
        self.assertEqual(result, b"hello")

    def test_get_output_bad_exit(self):
        """
        ``get_output()`` raises ``IOError`` if subprocess has non-zero exit
        code.
        """
        node = ProcessNode(initial_command_arguments=[])
        nonexistent = self.mktemp()
        self.assertRaises(IOError, node.get_output, [b"ls", nonexistent])


@_if_root
def make_sshnode(test_case):
    """
    Create a ``ProcessNode`` that can SSH into the local machine.

    :param TestCase test_case: The test case to use.

    :return: A ``ProcessNode`` instance.
    """
    server = create_ssh_server(FilePath(test_case.mktemp()))
    test_case.addCleanup(server.restore)

    return ProcessNode.using_ssh(
        host=unicode(server.ip).encode("ascii"), port=server.port,
        username=getuser(), private_key=server.key_path)


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
            with node.run([b"/bin/echo -n hello > " + temp_file.path]):
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
            with node.run([b"cat > " + temp_file.path]) as stdin:
                stdin.write(b"hello ")
                stdin.write(b"there")
            return temp_file.getContent()
        d = deferToThread(go)

        def got_data(data):
            self.assertEqual(data, b"hello there")
        d.addCallback(got_data)
        return d
