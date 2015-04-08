# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for certification logic in ``flocker.ca._ca``
"""

import datetime
import os

from Crypto.Util import asn1
from OpenSSL import crypto

from twisted.trial.unittest import SynchronousTestCase
from twisted.python.filepath import FilePath

from .. import CertificateAuthority, PathError, EXPIRY_20_YEARS


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
        path.makedirs()
        CertificateAuthority.initialize(path, b"mycluster")
        self.assertEqual(
            (True, True),
            (path.child("cluster.crt").exists(),
             path.child("cluster.crt").exists())
        )

    def test_decoded_certificate_matches_public_key(self):
        """
        A decoded certificate's public key matches the public key it is
        meant to be paired with.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        ca = CertificateAuthority.initialize(path, b"mycluster")
        self.assertTrue(
            ca.keypair.keypair.matches(ca.certificate.getPublicKey())
        )

    def test_decoded_certificate_matches_private_key(self):
        """
        A decoded certificate matches the private key it is meant to
        be paired with.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        ca = CertificateAuthority.initialize(path, b"mycluster")
        priv = ca.keypair.keypair.original
        pub = ca.certificate.getPublicKey().original
        pub_asn1 = crypto.dump_privatekey(crypto.FILETYPE_ASN1, pub)
        priv_asn1 = crypto.dump_privatekey(crypto.FILETYPE_ASN1, priv)
        pub_der = asn1.DerSequence()
        pub_der.decode(pub_asn1)
        priv_der = asn1.DerSequence()
        priv_der.decode(priv_asn1)
        pub_modulus = pub_der[1]
        priv_modulus = priv_der[1]
        self.assertEqual(pub_modulus, priv_modulus)

    def test_written_keypair_reloads(self):
        """
        A keypair written by ``CertificateAuthority.initialize`` can be
        successfully reloaded in to an identical ``CertificateAuthority``
        instance.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        ca1 = CertificateAuthority.initialize(path, b"mycluster")
        ca2 = CertificateAuthority.from_path(path)
        self.assertEqual(ca1, ca2)

    def test_keypair_correct_umask(self):
        """
        A keypair file written by ``CertificateAuthority.initialize`` has
        the correct permissions (0600).
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        CertificateAuthority.initialize(path, b"mycluster")
        keyPath = path.child(b"cluster.key")
        st = os.stat(keyPath.path)
        self.assertEqual(b'0600', oct(st.st_mode & 0777))

    def test_certificate_correct_umask(self):
        """
        A certificate file written by ``CertificateAuthority.initialize`` has
        the correct access masks set (0600).
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        CertificateAuthority.initialize(path, b"mycluster")
        keyPath = path.child(b"cluster.crt")
        st = os.stat(keyPath.path)
        self.assertEqual(b'0600', oct(st.st_mode & 0777))

    def test_create_error_on_non_existent_path(self):
        """
        An ``Exception`` is raised if the path given to
        ``CertificateAuthority.initialize`` does not exist.
        """
        path = FilePath(self.mktemp())
        e = self.assertRaises(
            PathError, CertificateAuthority.initialize, path, b"mycluster"
        )
        expected = b"Path {path} is not a directory.".format(path=path.path)
        self.assertEqual(str(e), expected)

    def test_load_error_on_non_existent_path(self):
        """
        An ``Exception`` is raised if the path given to
        ``CertificateAuthority.from_path`` does not exist.
        """
        path = FilePath(self.mktemp())
        e = self.assertRaises(
            PathError, CertificateAuthority.from_path, path
        )
        expected = b"Path {path} is not a directory.".format(path=path.path)
        self.assertEqual(str(e), expected)

    def test_certificate_is_self_signed(self):
        """
        A cert written by ``CertificateAuthority.initialize`` is validated
        as a self-signed certificate.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        ca = CertificateAuthority.initialize(path, b"mycluster")
        cert = ca.certificate.original
        issuer = cert.get_issuer().get_components()
        subject = cert.get_subject().get_components()
        self.assertEqual(issuer, subject)

    def test_certificate_expiration(self):
        """
        A cert written by ``CertificateAuthority.initialize`` has an expiry
        date 20 years from the date of signing.
        """
        today = datetime.datetime.now()
        expected_expiry = today + datetime.timedelta(seconds=EXPIRY_20_YEARS)
        path = FilePath(self.mktemp())
        path.makedirs()
        ca = CertificateAuthority.initialize(path, b"mycluster")
        cert = ca.certificate.original
        asn1 = cert.get_notAfter()
        expiry_date = datetime.datetime.strptime(asn1, "%Y%m%d%H%M%SZ")
        self.assertEqual(expiry_date.date(), expected_expiry.date())

    def test_certificate_is_rsa_4096_sha_256(self):
        """
        A cert written by ``CertificateAuthority.initialize`` is an RSA
        4096 bit, SHA-256 format.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        ca = CertificateAuthority.initialize(path, b"mycluster")
        cert = ca.certificate.original
        key = ca.certificate.getPublicKey().original
        self.assertEqual(
            (crypto.TYPE_RSA, 4096, b'sha256WithRSAEncryption'),
            (key.type(), key.bits(), cert.get_signature_algorithm())
        )
