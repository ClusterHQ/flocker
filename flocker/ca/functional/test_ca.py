# Copyright Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Functional tests for ``flocker-ca`` CLI.
"""

from subprocess import check_output, CalledProcessError

from twisted.python.procutils import which

from ...testtools import make_script_tests

EXECUTABLE = b"flocker-ca"


def requireCA(test):
    """
    Simple test decorator to check if flocker-ca is installed and skip
    if it isn't.
    """
    def inner(testcase, *args, **kwargs):
        if not which(EXECUTABLE):
            return testcase.skipTest(EXECUTABLE + " not installed")
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
    except CalledProcessError as e:
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
