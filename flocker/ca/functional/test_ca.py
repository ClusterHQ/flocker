# Copyright Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Functional tests for ``flocker-ca`` CLI.
"""

import re
from subprocess import CalledProcessError
from unittest import skipUnless

from eliot import Message, Logger

from twisted.python.filepath import FilePath
from twisted.python.procutils import which

from .._script import CAOptions

from ...testtools import make_script_tests, run_process

EXECUTABLE = b"flocker-ca"


def flocker_ca(command, *args, **kwargs):
    """
    Run a flocker-ca command and return the output along with an indicator
    as to whether or not the command succeeded.

    :param str command: The flocker-ca subcommand to execute.
    :param args: Additional parameters to pass to the command.
    :return: A ``tuple`` containing the integer return code and
        string output.
    """
    command = [EXECUTABLE, command] + list(args)
    try:
        result = run_process(command, **kwargs)
        output = result.output
        status = 0
    except CalledProcessError as e:
        Message.new(
            message_type="flocker.ca.functional:ca_initialize_error",
            error=str(e)).write(Logger())
        output = e.output
        status = e.returncode
    return (status, output)


def openssl_verify(cafile, certificatefile, **kwargs):
    """
    Use OpenSSL CLI to verify a certificate was signed by a given certificate
    authority.

    :param str cafile: The name of the certificate authority file.
    :param str certificatefile: The name of the certificate file to be checked
        against the supplied authority.
    :return: A ``bool`` that is True if the certificate was verified,
        otherwise False if verification failed or an error occurred.
    """
    command = [b"openssl", b"verify", b"-CAfile", cafile, certificatefile]
    try:
        result = run_process(command, **kwargs)
        return result.output.strip() == b"{}: OK".format(certificatefile)
    except CalledProcessError as e:
        result = run_process([
            "openssl", "x509", "-text", "-in", cafile], **kwargs)
        cafile_info = result.output
        result = run_process([
            "openssl", "x509", "-text", "-in", certificatefile], **kwargs)
        certificate_info = result.output
        error = str(e)
        error = error + "\n" + cafile_info + "\n" + certificate_info
        Message.new(
            message_type="flocker.ca.functional:openssl_verify_error",
            error=error).write(Logger())
        return False


class FlockerCATests(make_script_tests(EXECUTABLE)):
    """
    Tests for ``flocker-ca`` script.
    """
    @skipUnless(which(EXECUTABLE), EXECUTABLE + " not installed")
    @skipUnless(which(b"openssl"), "openssl not installed")
    def setUp(self):
        """
        Create a root certificate for the test.
        """
        self.temp_path = FilePath(self.mktemp())
        self.temp_path.makedirs()
        flocker_ca(b"initialize", b"mycluster", cwd=self.temp_path.path)

    def test_initialize(self):
        """
        Test for ``flocker-ca initialize`` command.
        Runs ``flocker-ca initialize`` and calls ``openssl`` to verify the
        generated certificate is a self-signed certificate authority.
        """
        self.assertTrue(
            openssl_verify(
                b"cluster.crt", b"cluster.crt", cwd=self.temp_path.path)
        )

    def test_control_certificate(self):
        """
        Test for ``flocker-ca create-control-certificate`` command.
        Runs ``flocker-ca initialize`` followed by
        ``flocker-ca create-control-certificate` and calls ``openssl``
        to verify the generated control certificate and private key is
        signed by the previously generated certificate authority.
        """
        flocker_ca(
            b"create-control-certificate", b"my.example.com",
            cwd=self.temp_path.path
        )
        self.assertTrue(
            openssl_verify(
                b"cluster.crt", b"control-my.example.com.crt",
                cwd=self.temp_path.path
            )
        )

    def test_node_certificate(self):
        """
        Test for ``flocker-ca create-node-certificate`` command.
        Runs ``flocker-ca initialize`` followed by
        ``flocker-ca create-node-certificate` and calls ``openssl``
        to verify the generated node certificate and private key is
        signed by the previously generated certificate authority.
        """
        status, output = flocker_ca(
            b"create-node-certificate", cwd=self.temp_path.path)
        # Find the generated file name with UUID from the output.
        file_pattern = re.compile("([a-zA-Z0-9\-]*\.crt)")
        file_name = file_pattern.search(output).groups()[0]
        self.assertTrue(
            openssl_verify(
                b"cluster.crt", file_name, cwd=self.temp_path.path)
        )

    def test_apiuser_certificate(self):
        """
        Test for ``flocker-ca create-api-certificate`` command.
        Runs ``flocker-ca initialize`` followed by
        ``flocker-ca create-api-certificate` and calls ``openssl``
        to verify the generated control certificate and private key is
        signed by the previously generated certificate authority.
        """
        flocker_ca(
            b"create-api-certificate", b"alice", cwd=self.temp_path.path)
        self.assertTrue(
            openssl_verify(
                b"cluster.crt", b"alice.crt", cwd=self.temp_path.path)
        )

    def test_help_description(self):
        """
        The output of ``flocker-ca --help`` includes the helptext with
        its original formatting.
        """
        helptext = CAOptions.helptext
        expected = ""
        for line in helptext.splitlines():
            expected = expected + line.strip() + "\n"
        status, output = flocker_ca(b"--help")
        self.assertIn(expected, output)
