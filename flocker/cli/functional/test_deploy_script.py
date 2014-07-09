# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for the ``flocker-deploy`` command line tool.
"""
from subprocess import check_output
from unittest import skipUnless

from yaml import safe_dump

from twisted.python.procutils import which
from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase

from ...testtools import create_ssh_server, FakeSysModule
from .._sshconfig import OpenSSHConfiguration

from ..script import DeployScript, DeployOptions
from ...common.script import FlockerScriptRunner

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

	deployment_configuration_file = FilePath(self.mktemp())
	deployment_configuration_file.setContent(
	    safe_dump(deployment_configuration)
	)
	application_configuration_file = FilePath(self.mktemp())
	application_configuration_file.setContent(
	    safe_dump(application_configuration)
	)

	#result = check_output([b"flocker-deploy"] + [application_configuration_file.path, deployment_configuration_file.path])
        fake_sys_module = FakeSysModule(argv=[b"flocker-deploy", application_configuration_file.path, deployment_configuration_file.path]) 
        script_runner = FlockerScriptRunner(
            script = DeployScript(ssh_configuration=self.config, ssh_port=self.server.port),
            options = DeployOptions(),
            sys_module = fake_sys_module
        )
	self.assertRaises(SystemExit, script_runner.main)
	import pdb;pdb.set_trace()
