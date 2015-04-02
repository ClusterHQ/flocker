# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for certification logic in ``flocker.ca._ca``
"""

from twisted.trial.unittest import SynchronousTestCase
from twisted.python.filepath import FilePath

from .. import CertificateAuthority


class CertificateAuthorityTests(SynchronousTestCase):
    """
    Tests for ``flocker.ca._ca.CertificateAuthority``.
    """

    def test_written_keypair_exists(self):
        """
        ``CertificateAuthority.initialize`` writes a PEM file to the
        specified path.
        """
        path = FilePath(self.mktemp())
        CertificateAuthority.initialize(path, b"mycluster")
        self.assertEqual(
            (True, True),
            (path.child("cluster.pem").exists(),
             path.child("cluster.crt").exists())
        )

    def test_written_keypair_reloads(self):
        """
        A keypair written by ``CertificateAuthority.initialize`` can be
        successfully reloaded in to a ``CertificateAuthority`` instance.
        """
        path = FilePath(self.mktemp())
        ca1 = CertificateAuthority.initialize(path, b"mycluster")
        ca2 = CertificateAuthority(path)
        self.assertEqual(ca1, ca2)

    def test_keypair_correct_umask(self):
        """
        A keypair file written by ``CertificateAuthority.initialize`` has
        the correct access masks set (0600).
        """
        pass

    def test_certificate_correct_umask(self):
        """
        A certificate file written by ``CertificateAuthority.initialize`` has
        the correct access masks set (0600).
        """
        pass

    def test_error_on_non_existent_path(self):
        """
        An ``Exception`` is raised if the path given to
        ``CertificateAuthority.initialize`` does not exist.
        """
        pass

    def test_certificate_is_signed(self):
        """
        A cert written by ``CertificateAuthority.initialize`` is validated
        as a self-signed certificate.
        """
        pass

    def test_certificate_expiration(self):
        """
        A cert written by ``CertificateAuthority.initialize`` has an expiry
        date 20 years from the date of signing.
        """
        pass

    def test_certificate_is_rsa_4096_sha_256(self):
        """
        A cert written by ``CertificateAuthority.initialize`` is an RSA
        4096 bit, SHA-256 format.
        """
        pass
