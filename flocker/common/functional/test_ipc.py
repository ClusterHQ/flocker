# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for IPC.
"""

from twisted.internet.threads import deferToThread
from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase

from .. import ProcessNode
from ..test.test_ipc import make_inode_tests
from ...testtools.ssh import create_ssh_server


def make_prefixless_processnode(test_case):
    """
    Create a ``ProcessNode`` that just runs the given command with no
    prefix.

    :return: ``ProcessNode`` instance.
    """
    return ProcessNode(initial_command_arguments=[])


class ProcessINodeTests(make_inode_tests(make_prefixless_processnode)):
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
        with node.run([b"-c", b"echo hello > " + temp_file]):
            pass
        self.assertEqual(FilePath(temp_file).getContent(), b"hello\n")

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
        node.get_output([b"-c", b"echo hello > " + temp_file])
        self.assertEqual(FilePath(temp_file).getContent(), b"hello\n")

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
        username=b"root", private_key=server.key_path)


class SSHProcessNodeTests(TestCase):
    """Tests for ``ProcessNode.with_ssh``."""

    def test_runs_command(self):
        """
        ``run()`` on a SSH ``ProcessNode`` runs the command on the machine
        being ssh'd into.
        """
        node = make_sshnode(self)
        temp_file = FilePath(self.mktemp())

        def go():
            with node.run([b"python", b"-c",
                           b"file('%s', 'w').write(b'hello')"
                           % (temp_file.path,)]):
                pass
            return temp_file.getContent()
        d = deferToThread(go)

        def got_data(data):
            self.assertEqual(data, b"hello")
        d.addCallback(got_data)
        return d

    def test_run_stdin(self):
        """
        ``run()`` on a SSH ``ProcessNode`` writes to the remote command's
        stdin.
        """
        node = make_sshnode(self)
        temp_file = FilePath(self.mktemp())

        def go():
            with node.run([b"python", b"-c",
                           b"import sys; "
                           b"file('%s', 'wb').write(sys.stdin.read())"
                           % (temp_file.path,)]) as stdin:
                stdin.write(b"hello ")
                stdin.write(b"there")
            return temp_file.getContent()
        d = deferToThread(go)

        def got_data(data):
            self.assertEqual(data, b"hello there")
        d.addCallback(got_data)
        return d

    def test_get_output(self):
        """
        ``get_output()`` returns the command's output.
        """
        node = make_sshnode(self)
        temp_file = FilePath(self.mktemp())
        temp_file.setContent(b"hello!")

        def go():
            return node.get_output([b"python", b"-c",
                                    b"import sys; "
                                    b"sys.stdout.write(file('%s').read())"
                                    % (temp_file.path,)])
        d = deferToThread(go)

        def got_data(data):
            self.assertEqual(data, b"hello!")
        d.addCallback(got_data)
        return d


class MutatingProcessNode(ProcessNode):
    """Mutate the command being run in order to make tests work.

    Come up with something better in
    https://clusterhq.atlassian.net/browse/FLOC-125
    """
    def __init__(self, to_service):
        """
        :param to_service: The VolumeService to which a push is being done.
        """
        self.to_service = to_service
        ProcessNode.__init__(self, initial_command_arguments=[])

    def _mutate(self, remote_command):
        """
        Add the pool and mountpoint arguments, which aren't necessary in real
        code.

        :param remote_command: Original command arguments.

        :return: Modified command arguments.
        """
        return remote_command[:1] + [
            b"--pool", self.to_service.pool._name,
            b"--mountpoint", self.to_service.pool._mount_root.path
        ] + remote_command[1:]

    def run(self, remote_command):
        return ProcessNode.run(self, self._mutate(remote_command))

    def get_output(self, remote_command):
        return ProcessNode.get_output(self, self._mutate(remote_command))
