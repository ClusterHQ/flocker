# Copyright Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Functional tests for ``flocker-ca`` CLI.
"""

import re

from subprocess import check_output, CalledProcessError

from twisted.python.procutils import which

from .._script import CAOptions

from ...testtools import make_script_tests

EXECUTABLE = b"flocker-ca"


def requireCA(test):
    """
    Simple test decorator to check if both flocker-ca and OpenSSL are
    installed and skip if either isn't.
    """
    def inner(testcase, *args, **kwargs):
        if not which(EXECUTABLE):
            return testcase.skipTest(EXECUTABLE + " not installed")
        if not which(b"openssl"):
            return testcase.skipTest("openssl not installed")
        return test(testcase, *args, **kwargs)
    return inner


def flocker_ca(command, *args):
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
        output = check_output(command)
        status = 0
    except CalledProcessError as e:
        output = e.output
        status = e.returncode
    return (status, output)


def openssl_verify(cafile, certificatefile):
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
        output = check_output(command)
        return output.strip() == b"{}: OK".format(certificatefile)
    except CalledProcessError:
        return False


class FlockerCATests(make_script_tests(EXECUTABLE)):
    """
    Tests for ``flocker-ca`` script.
    """
    @requireCA
    def test_initialize(self):
        """
        Test for ``flocker-ca initialize`` command.
        Runs ``flocker-ca initialize`` and calls ``openssl`` to verify the
        generated certificate is a self-signed certificate authority.
        """
        flocker_ca("initialize", "mycluster")
        self.assertTrue(
            openssl_verify("cluster.crt", "cluster.crt")
        )

    @requireCA
    def test_control_certificate(self):
        """
        Test for ``flocker-ca create-control-certificate`` command.
        Runs ``flocker-ca initialize`` followed by
        ``flocker-ca create-control-certificate` and calls ``openssl``
        to verify the generated control certificate and private key is
        signed by the previously generated certificate authority.
        """
        flocker_ca("initialize", "mycluster")
        flocker_ca("create-control-certificate")
        self.assertTrue(
            openssl_verify("cluster.crt", "control-service.crt")
        )

    @requireCA
    def test_node_certificate(self):
        """
        Test for ``flocker-ca create-node-certificate`` command.
        Runs ``flocker-ca initialize`` followed by
        ``flocker-ca create-node-certificate` and calls ``openssl``
        to verify the generated node certificate and private key is
        signed by the previously generated certificate authority.
        """
        flocker_ca("initialize", "mycluster")
        status, output = flocker_ca("create-node-certificate")
        # Find the generated file name with UUID from the output.
        file_pattern = re.compile("([a-zA-Z0-9\-]*\.crt)")
        file_name = file_pattern.search(output).groups()[0]
        self.assertTrue(
            openssl_verify("cluster.crt", file_name)
        )

    @requireCA
    def test_apiuser_certificate(self):
        """
        Test for ``flocker-ca create-api-certificate`` command.
        Runs ``flocker-ca initialize`` followed by
        ``flocker-ca create-api-certificate` and calls ``openssl``
        to verify the generated control certificate and private key is
        signed by the previously generated certificate authority.
        """
        flocker_ca("initialize", "mycluster")
        flocker_ca("create-api-certificate", "alice")
        self.assertTrue(
            openssl_verify("cluster.crt", "alice.crt")
        )

    @requireCA
    def test_help_description(self):
        """
        The output of ``flocker-ca --help`` includes the helptext with
        its original formatting.
        """
        helptext = CAOptions.helptext
        expected = ""
        for line in helptext.splitlines():
            expected = expected + line.strip() + "\n"
        status, output = flocker_ca("--help")
        self.assertIn(expected, output)
