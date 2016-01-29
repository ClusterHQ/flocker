"""
Tests for ``flocker.provision._ssh._conch``.
"""

from txeffect import perform

from eliot.testing import capture_logging, assertHasMessage

from twisted.python.filepath import FilePath

from .._ssh import run, put, run_remotely
from .._ssh._conch import make_dispatcher, RUN_OUTPUT_MESSAGE
from ...testtools import AsyncTestCase

from flocker.testtools.ssh import create_ssh_server, create_ssh_agent

skip = "See FLOC-1883. These tests don't properly clean up the reactor."


class Tests(AsyncTestCase):
    """
    Tests for conch implementation of ``flocker.provision._ssh.RunRemotely``.
    """

    def setUp(self):
        super(Tests, self).setUp()
        self.sshd_config = FilePath(self.mktemp())
        self.server = create_ssh_server(self.sshd_config)
        self.addCleanup(self.server.restore)

        self.agent = create_ssh_agent(self.server.key_path)
        self.addCleanup(self.agent.restore)

    def test_run(self):
        """
        The ``Run`` intent runs the specified command via ssh.
        """
        command = run_remotely(
            username="root",
            address=str(self.server.ip),
            port=self.server.port,
            commands=run("touch hello"),
        )

        d = perform(
            make_dispatcher(self.reactor),
            command,
        )

        def check(_):
            self.assertEqual(self.server.home.child('hello').getContent(),
                             "")
        return d

    def test_put(self):
        """
        The ``Put`` intent puts the provided contents in the specified file.
        """
        content = '\\hell%o'
        command = run_remotely(
            username="root",
            address=str(self.server.ip),
            port=self.server.port,
            commands=put(content=content, path="file"),
        )

        d = perform(
            make_dispatcher(self.reactor),
            command,
        )

        def check(_):
            self.assertEqual(self.server.home.child('file').getContent(),
                             content)
        d.addCallback(check)
        return d

    @capture_logging(
        assertHasMessage, RUN_OUTPUT_MESSAGE,
        {'line': 'test_ssh_conch:test_run_logs_stdout'})
    def test_run_logs_stdout(self, logger):
        """
        The ``Run`` intent logs the standard output of the specified command.
        """
        command = run_remotely(
            username="root",
            address=str(self.server.ip),
            port=self.server.port,
            commands=run("echo test_ssh_conch:test_run_logs_stdout 1>&2"),
        )

        d = perform(
            make_dispatcher(self.reactor),
            command,
        )
        return d

    @capture_logging(
        assertHasMessage, RUN_OUTPUT_MESSAGE,
        {'line': 'test_ssh_conch:test_run_logs_stderr'})
    def test_run_logs_stderr(self, logger):
        """
        The ``Run`` intent logs the standard output of the specified command.
        """
        command = run_remotely(
            username="root",
            address=str(self.server.ip),
            port=self.server.port,
            commands=run("echo test_ssh_conch:test_run_logs_stderr 1>&2"),
        )

        d = perform(
            make_dispatcher(self.reactor),
            command,
        )
        return d
