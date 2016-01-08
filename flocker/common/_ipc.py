# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Inter-process communication for flocker.
"""

from subprocess import Popen, PIPE, check_output, CalledProcessError
from contextlib import contextmanager
from io import BytesIO
from threading import current_thread
from pipes import quote

from zope.interface import Interface, implementer

from characteristic import with_cmp, with_repr


class INode(Interface):
    """
    A remote node with which this node can communicate.
    """

    def run(remote_command):
        """Context manager that runs a remote command and return its stdin.

        The returned file-like object will be closed by this object.

        :param remote_command: ``list`` of ``bytes``, the command to run
            remotely along with its arguments.

        :return: file-like object that can be written to.
        """

    def get_output(remote_command):
        """Run a remote command and return its stdout.

        May raise an exception if an error of some sort occured.

        :param remote_command: ``list`` of ``bytes``, the command to run
            remotely along with its arguments.

        :return: ``bytes`` of stdout from the remote command.
        """


@with_cmp(["initial_command_arguments"])
@with_repr(["initial_command_arguments"])
@implementer(INode)
class ProcessNode(object):
    """
    Communicate with a remote node using a subprocess.
    """
    def __init__(self, initial_command_arguments, quote=lambda d: d):
        """
        :param initial_command_arguments: ``tuple`` of ``bytes``, initial
            command arguments to prefix to whatever arguments get passed to
           ``run()``.

        :param quote: Callable that transforms the non-initial command
            arguments, converting a list of ``bytes`` to a list of
            ``bytes``. By default does nothing.
        """
        self.initial_command_arguments = tuple(initial_command_arguments)
        self._quote = quote

    @contextmanager
    def run(self, remote_command):
        process = Popen(
            self.initial_command_arguments +
            tuple(map(self._quote, remote_command)),
            stdin=PIPE)
        try:
            yield process.stdin
        finally:
            process.stdin.close()
            exit_code = process.wait()
            if exit_code:
                # We should really capture this and stderr better:
                # https://clusterhq.atlassian.net/browse/FLOC-155
                raise IOError("Bad exit", remote_command, exit_code)

    def get_output(self, remote_command):
        try:
            return check_output(
                self.initial_command_arguments +
                tuple(map(self._quote, remote_command)))
        except CalledProcessError as e:
            # We should really capture this and stderr better:
            # https://clusterhq.atlassian.net/browse/FLOC-155
            raise IOError("Bad exit", remote_command, e.returncode, e.output)

    @classmethod
    def using_ssh(cls, host, port, username, private_key):
        """Create a ``ProcessNode`` that communicate over SSH.

        :param bytes host: The hostname or IP.
        :param int port: The port number of the SSH server.
        :param bytes username: The username to SSH as.
        :param FilePath private_key: Path to private key to use when talking to
            SSH server.

        :return: ``ProcessNode`` instance that communicates over SSH.
        """
        return cls(initial_command_arguments=(
            b"ssh",
            b"-q",  # suppress warnings
            b"-i", private_key.path,
            b"-l", username,
            # We're ok with unknown hosts; we'll be switching away from
            # SSH by the time Flocker is production-ready and security is
            # a concern.
            b"-o", b"StrictHostKeyChecking=no",
            # The tests hang if ControlMaster is set, since OpenSSH won't
            # ever close the connection to the test server.
            b"-o", b"ControlMaster=no",
            # Some systems (notably Ubuntu) enable GSSAPI authentication which
            # involves a slow DNS operation before failing and moving on to a
            # working mechanism.  The expectation is that key-based auth will
            # be in use so just jump straight to that.  An alternate solution,
            # explicitly disabling GSSAPI, has cross-version platform and
            # cross-version difficulties (the options aren't always recognized
            # and result in an immediate failure).  As mentioned above, we'll
            # switch away from SSH soon.
            b"-o", b"PreferredAuthentications=publickey",
            b"-p", b"%d" % (port,), host), quote=quote)


@implementer(INode)
class FakeNode(object):
    """
    Pretend to run a command.

    This is useful for testing.

    :ivar remote_command: The arguments to the last call to ``run()`` or
        ``get_output()``.

    :ivar stdin: `BytesIO` returned from last call to ``run()``.

    :ivar thread_id: The ID of the thread ``run()`` or ``get_output()``
        ran in.
    """
    def __init__(self, outputs=()):
        """
        :param outputs: Sequence of results for ``get_output()``, either
            exceptions or ``bytes``. Exceptions will be raised, otherwise the
            object will be returned.
        """
        self._outputs = list(outputs)

    @contextmanager
    def run(self, remote_command):
        """
        Store arguments and in-memory "stdin".
        """
        self.thread_id = current_thread().ident
        self.stdin = BytesIO()
        self.remote_command = remote_command
        yield self.stdin
        self.stdin.seek(0, 0)

    def get_output(self, remote_command):
        """
        Return (or if an exception, raise) the next remaining output of the
        ones passed to the constructor.
        """
        self.thread_id = current_thread().ident
        self.remote_command = remote_command
        result = self._outputs.pop(0)
        if isinstance(result, Exception):
            raise result
        else:
            return result
