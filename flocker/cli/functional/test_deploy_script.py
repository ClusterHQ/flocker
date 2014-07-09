# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for the ``flocker-deploy`` command line tool.
"""
from subprocess import check_call, check_output
from unittest import skipUnless

from os import devnull, environ, kill
from signal import SIGKILL
from operator import setitem, delitem

from twisted.internet import reactor
from twisted.python.procutils import which
from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase

from ...testtools import create_ssh_server
from .._sshconfig import OpenSSHConfiguration
from ...node import model_from_configuration

from ..script import DeployScript

from ... import __version__


_require_installed = skipUnless(which("flocker-deploy"),
                                "flocker-deploy not installed")


class FlockerDeployTests(TestCase):
    """Tests for ``flocker-deploy``."""

    @_require_installed
    def setUp(self):
        self.ssh_config = FilePath(self.mktemp())
        self.server = create_ssh_server(self.ssh_config)
        self.addCleanup(self.server.restore)
        self.flocker_config = FilePath(self.mktemp())
        self.config = OpenSSHConfiguration(
            ssh_config_path=self.ssh_config,
            flocker_path=self.flocker_config)
        self.configure_ssh = self.config.configure_ssh

        output = check_output([b"ssh-agent", b"-c"]).splitlines()

        # ``configure_ssh`` expects ``ssh`` to already be able to
        # authenticate against the server.  Set up an ssh-agent to
        # help it do that against our testing server.

        # setenv SSH_AUTH_SOCK /tmp/ssh-5EfGti8RPQbQ/agent.6390;
        # setenv SSH_AGENT_PID 6391;
        # echo Agent pid 6391;
        sock = output[0].split()[2][:-1]
        pid = output[1].split()[2][:-1]

        self.addCleanup(lambda: kill(int(pid), SIGKILL))

        def patchdict(k, v):
            if k in environ:
                self.addCleanup(
                    lambda old=environ[k]: setitem(environ, k, old))
            else:
                self.addCleanup(lambda: delitem(environ, k))

            environ[k] = v

        patchdict(b"SSH_AUTH_SOCK", sock)
        patchdict(b"SSH_AGENT_PID", pid)

        with open(devnull, "w") as discard:
            # See https://github.com/clusterhq/flocker/issues/192
            check_call(
                [b"ssh-add", self.server.key_path.path],
                stdout=discard, stderr=discard)


    def test_version(self):
        """``flocker-deploy --version`` returns the current version."""
        result = check_output([b"flocker-deploy"] + [b"--version"])
        self.assertEqual(result, b"%s\n" % (__version__,))

    def test_deploy(self):
        """
        ``flocker-deploy`` connects to each of the nodes in the supplied
        deployment configuration file.
        """
        deployment_configuration = {
            "version": 1,
            "nodes": {
                str(self.server.ip): ["mysql-hybridcluster"],
            }
        }
        application_configuration = {
            "version": 1,
            "applications": {
                "mysql-hybridcluster": {
                    "image": "flocker/flocker:v1.0"
                }
            }
        }

        script = DeployScript(ssh_configuration=self.config, ssh_port=self.server.port)
        options = {"deployment": model_from_configuration(application_configuration, deployment_configuration)}
        result = script.main(reactor, options)
        return result
