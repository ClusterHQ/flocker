# Copyright Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for certification logic in ``flocker.ca._ca``
"""

import datetime
import os

from uuid import uuid4

from Crypto.Util import asn1
from OpenSSL import crypto

from twisted.trial.unittest import SynchronousTestCase
from twisted.python.filepath import FilePath

from .. import (RootCredential, ControlCredential, NodeCredential,
                UserCredential, PathError, EXPIRY_20_YEARS,
                AUTHORITY_CERTIFICATE_FILENAME, AUTHORITY_KEY_FILENAME,
                CONTROL_CERTIFICATE_FILENAME, CONTROL_KEY_FILENAME)

from ...testtools import not_root, skip_on_broken_permissions


class UserCredentialTests(SynchronousTestCase):
    """
    Tests for ``flocker.ca._ca.UserCredential``.
    """
    def setUp(self):
        """
        Generate a RootCredential for the API certificate tests
        to work with.
        """
        self.path = FilePath(self.mktemp())
        self.path.makedirs()
        self.ca = RootCredential.initialize(self.path, b"mycluster")
        self.username = b"alice"

    def test_written_keypair_exists(self):
        """
        ``UserCredential.initialize`` writes a PEM file to the
        specified path.
        """
        uc = UserCredential.initialize(self.path, self.ca, self.username)
        cert_file = b"{user}.crt".format(user=uc.username)
        key_file = b"{user}.key".format(user=uc.username)
        self.assertEqual(
            (True, True),
            (self.path.child(cert_file).exists(),
             self.path.child(key_file).exists())
        )

    def test_decoded_certificate_matches_public_key(self):
        """
        A decoded certificate's public key matches the public key it is
        meant to be paired with.
        """
        uc = UserCredential.initialize(self.path, self.ca, self.username)
        self.assertTrue(
            uc.credential.keypair.keypair.matches(
                uc.credential.certificate.getPublicKey())
        )

    def test_decoded_certificate_matches_private_key(self):
        """
        A decoded certificate matches the private key it is meant to
        be paired with.
        """
        uc = UserCredential.initialize(self.path, self.ca, self.username)
        priv = uc.credential.keypair.keypair.original
        pub = uc.credential.certificate.getPublicKey().original
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
        A keypair written by ``UserCredential.initialize`` can be
        successfully reloaded in to an identical ``ControlCertificate``
        instance.
        """
        uc1 = UserCredential.initialize(self.path, self.ca, self.username)
        uc2 = UserCredential.from_path(self.path, uc1.username)
        self.assertEqual(uc1, uc2)

    def test_keypair_correct_umask(self):
        """
        A keypair file written by ``UserCredential.initialize`` has
        the correct permissions (0600).
        """
        uc = UserCredential.initialize(self.path, self.ca, self.username)
        key_file = b"{user}.key".format(user=uc.username)
        keyPath = self.path.child(key_file)
        st = os.stat(keyPath.path)
        self.assertEqual(b'0600', oct(st.st_mode & 0777))

    def test_certificate_correct_permission(self):
        """
        A certificate file written by ``UserCredential.initialize`` has
        the correct access mode set (0600).
        """
        uc = UserCredential.initialize(self.path, self.ca, self.username)
        key_file = b"{user}.key".format(user=uc.username)
        keyPath = self.path.child(key_file)
        st = os.stat(keyPath.path)
        self.assertEqual(b'0600', oct(st.st_mode & 0777))

    def test_create_error_on_non_existent_path(self):
        """
        A ``PathError`` is raised if the path given to
        ``UserCredential.initialize`` does not exist.
        """
        path = FilePath(self.mktemp())
        e = self.assertRaises(
            PathError, UserCredential.initialize, path, self.ca, self.username
        )
        expected = (b"Unable to write certificate file. "
                    b"No such file or directory {path}").format(
                        path=path.child("{}.crt".format(self.username)).path)
        self.assertEqual(str(e), expected)

    def test_load_error_on_non_existent_path(self):
        """
        A ``PathError`` is raised if the path given to
        ``UserCredential.from_path`` does not exist.
        """
        path = FilePath(self.mktemp())
        e = self.assertRaises(
            PathError, UserCredential.from_path, path, self.username
        )
        expected = (b"Certificate file could not be opened. "
                    b"No such file or directory {path}").format(
                        path=path.child("{}.crt".format(self.username)).path)
        self.assertEqual(str(e), expected)

    def test_load_error_on_non_existent_certificate_file(self):
        """
        A ``PathError`` is raised if the certificate file path given to
        ``UserCredential.from_path`` does not exist.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        cert_file = b"{user}.crt".format(user=self.username)
        e = self.assertRaises(
            PathError, UserCredential.from_path, path, self.username
        )
        expected = (b"Certificate file could not be opened. "
                    b"No such file or directory "
                    b"{path}").format(
            path=path.child(cert_file).path)
        self.assertEqual(str(e), expected)

    def test_load_error_on_non_existent_key_file(self):
        """
        A ``PathError`` is raised if the key file path given to
        ``UserCredential.from_path`` does not exist.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        cert_file = b"{user}.crt".format(user=self.username)
        key_file = b"{user}.key".format(user=self.username)
        crt_path = path.child(cert_file)
        crt_file = crt_path.open(b'w')
        crt_file.write(b"dummy")
        crt_file.close()
        e = self.assertRaises(
            PathError, UserCredential.from_path, path, self.username
        )
        expected = (b"Private key file could not be opened. "
                    b"No such file or directory "
                    b"{path}").format(
                        path=path.child(key_file).path)
        self.assertEqual(str(e), expected)

    @not_root
    @skip_on_broken_permissions
    def test_load_error_on_unreadable_certificate_file(self):
        """
        A ``PathError`` is raised if the certificate file path given to
        ``UserCredential.from_path`` cannot be opened for reading.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        cert_file = b"{user}.crt".format(user=self.username)
        key_file = b"{user}.key".format(user=self.username)
        crt_path = path.child(cert_file)
        crt_file = crt_path.open(b'w')
        crt_file.write(b"dummy")
        crt_file.close()
        # make file unreadable
        crt_path.chmod(64)
        key_path = path.child(key_file)
        key_file = key_path.open(b'w')
        key_file.write(b"dummy")
        key_file.close()
        # make file unreadable
        key_path.chmod(64)
        e = self.assertRaises(
            PathError, UserCredential.from_path, path, self.username
        )
        expected = (
            b"Certificate file could not be opened. "
            b"Permission denied {path}"
        ).format(path=crt_path.path)
        self.assertEqual(str(e), expected)

    @not_root
    @skip_on_broken_permissions
    def test_load_error_on_unreadable_key_file(self):
        """
        A ``PathError`` is raised if the key file path given to
        ``UserCredential.from_path`` cannot be opened for reading.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        cert_file = b"{user}.crt".format(user=self.username)
        key_file = b"{user}.key".format(user=self.username)
        crt_path = path.child(cert_file)
        crt_file = crt_path.open(b'w')
        crt_file.write(b"dummy")
        crt_file.close()
        key_path = path.child(key_file)
        key_file = key_path.open(b'w')
        key_file.write(b"dummy")
        key_file.close()
        # make file unreadable
        key_path.chmod(64)
        e = self.assertRaises(
            PathError, UserCredential.from_path, path, self.username
        )
        expected = (
            b"Private key file could not be opened. "
            b"Permission denied {path}"
        ).format(path=key_path.path)
        self.assertEqual(str(e), expected)

    def test_certificate_subject_username(self):
        """
        A cert written by ``UserCredential.initialize`` has the
        subject common name "user-{user}" where {user} is the username
        supplied during the certificate's creation.
        """
        uc = UserCredential.initialize(self.path, self.ca, self.username)
        cert = uc.credential.certificate.original
        subject = cert.get_subject()
        self.assertEqual(subject.CN, b"user-{user}".format(user=uc.username))

    def test_certificate_ou_matches_ca(self):
        """
        A cert written by ``UserCredential.initialize`` has the issuing
        authority's common name as its organizational unit name.
        """
        uc = UserCredential.initialize(self.path, self.ca, self.username)
        cert = uc.credential.certificate.original
        issuer = cert.get_issuer()
        subject = cert.get_subject()
        self.assertEqual(
            issuer.CN,
            subject.OU
        )

    def test_certificate_is_signed_by_ca(self):
        """
        A cert written by ``UserCredential.initialize`` is validated
        as being signed by the certificate authority.
        """
        uc = UserCredential.initialize(self.path, self.ca, self.username)
        cert = uc.credential.certificate.original
        issuer = cert.get_issuer()
        self.assertEqual(
            issuer.CN,
            self.ca.credential.certificate.getSubject().CN
        )

    def test_certificate_expiration(self):
        """
        A cert written by ``UserCredential.initialize`` has an expiry
        date 20 years from the date of signing.
        """
        today = datetime.datetime.now()
        expected_expiry = today + datetime.timedelta(seconds=EXPIRY_20_YEARS)
        uc = UserCredential.initialize(self.path, self.ca, self.username)
        cert = uc.credential.certificate.original
        asn1 = cert.get_notAfter()
        expiry_date = datetime.datetime.strptime(asn1, "%Y%m%d%H%M%SZ")
        self.assertEqual(expiry_date.date(), expected_expiry.date())

    def test_certificate_is_rsa_4096_sha_256(self):
        """
        A cert written by ``UserCredential.initialize`` is an RSA
        4096 bit, SHA-256 format.
        """
        uc = UserCredential.initialize(self.path, self.ca, self.username)
        cert = uc.credential.certificate.original
        key = uc.credential.certificate.getPublicKey().original
        self.assertEqual(
            (crypto.TYPE_RSA, 4096, b'sha256WithRSAEncryption'),
            (key.type(), key.bits(), cert.get_signature_algorithm())
        )


class NodeCredentialTests(SynchronousTestCase):
    """
    Tests for ``flocker.ca._ca.NodeCredential``.
    """
    def setUp(self):
        """
        Generate a RootCredential for the node certificate tests
        to work with.
        """
        self.path = FilePath(self.mktemp())
        self.path.makedirs()
        self.ca = RootCredential.initialize(self.path, b"mycluster")
        self.uuid = str(uuid4())

    def test_written_keypair_exists(self):
        """
        ``NodeCredential.initialize`` writes a PEM file to the
        specified path.
        """
        nc = NodeCredential.initialize(self.path, self.ca)
        cert_file = b"{uuid}.crt".format(uuid=nc.uuid)
        key_file = b"{uuid}.key".format(uuid=nc.uuid)
        self.assertEqual(
            (True, True),
            (self.path.child(cert_file).exists(),
             self.path.child(key_file).exists())
        )

    def test_decoded_certificate_matches_public_key(self):
        """
        A decoded certificate's public key matches the public key it is
        meant to be paired with.
        """
        nc = NodeCredential.initialize(self.path, self.ca)
        self.assertTrue(
            nc.credential.keypair.keypair.matches(
                nc.credential.certificate.getPublicKey())
        )

    def test_decoded_certificate_matches_private_key(self):
        """
        A decoded certificate matches the private key it is meant to
        be paired with.
        """
        nc = NodeCredential.initialize(self.path, self.ca)
        priv = nc.credential.keypair.keypair.original
        pub = nc.credential.certificate.getPublicKey().original
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
        A keypair written by ``NodeCredential.initialize`` can be
        successfully reloaded in to an identical ``ControlCertificate``
        instance.
        """
        nc1 = NodeCredential.initialize(self.path, self.ca)
        nc2 = NodeCredential.from_path(self.path, nc1.uuid)
        self.assertEqual(nc1, nc2)

    def test_keypair_correct_umask(self):
        """
        A keypair file written by ``NodeCredential.initialize`` has
        the correct permissions (0600).
        """
        nc = NodeCredential.initialize(self.path, self.ca)
        key_file = b"{uuid}.key".format(uuid=nc.uuid)
        keyPath = self.path.child(key_file)
        st = os.stat(keyPath.path)
        self.assertEqual(b'0600', oct(st.st_mode & 0777))

    def test_certificate_correct_permission(self):
        """
        A certificate file written by ``NodeCredential.initialize`` has
        the correct access mode set (0600).
        """
        nc = NodeCredential.initialize(self.path, self.ca)
        key_file = b"{uuid}.key".format(uuid=nc.uuid)
        keyPath = self.path.child(key_file)
        st = os.stat(keyPath.path)
        self.assertEqual(b'0600', oct(st.st_mode & 0777))

    def test_create_error_on_non_existent_path(self):
        """
        A ``PathError`` is raised if the path given to
        ``NodeCredential.initialize`` does not exist.
        """
        path = FilePath(self.mktemp())
        e = self.assertRaises(
            PathError, NodeCredential.initialize, path, self.ca
        )
        expected = (b"Unable to write certificate file. "
                    b"No such file or directory {path}").format(
                        path=e.filename)
        self.assertEqual(str(e), expected)

    def test_load_error_on_non_existent_path(self):
        """
        A ``PathError`` is raised if the path given to
        ``NodeCredential.from_path`` does not exist.
        """
        path = FilePath(self.mktemp())
        uuid = self.uuid
        e = self.assertRaises(
            PathError, NodeCredential.from_path, path, uuid
        )
        expected = (b"Certificate file could not be opened. "
                    b"No such file or directory {path}").format(
                        path=path.child("{}.crt".format(uuid)).path)
        self.assertEqual(str(e), expected)

    def test_load_error_on_non_existent_certificate_file(self):
        """
        A ``PathError`` is raised if the certificate file path given to
        ``NodeCredential.from_path`` does not exist.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        # random UUID that doesn't exist in path
        uuid = self.uuid
        cert_file = b"{uuid}.crt".format(uuid=uuid)
        e = self.assertRaises(
            PathError, NodeCredential.from_path, path, uuid
        )
        expected = (b"Certificate file could not be opened. "
                    b"No such file or directory "
                    b"{path}").format(
            path=path.child(cert_file).path)
        self.assertEqual(str(e), expected)

    def test_load_error_on_non_existent_key_file(self):
        """
        A ``PathError`` is raised if the key file path given to
        ``NodeCredential.from_path`` does not exist.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        # random UUID that doesn't exist in path
        uuid = self.uuid
        cert_file = b"{uuid}.crt".format(uuid=uuid)
        key_file = b"{uuid}.key".format(uuid=uuid)
        crt_path = path.child(cert_file)
        crt_file = crt_path.open(b'w')
        crt_file.write(b"dummy")
        crt_file.close()
        e = self.assertRaises(
            PathError, NodeCredential.from_path, path, uuid
        )
        expected = (b"Private key file could not be opened. "
                    b"No such file or directory "
                    b"{path}").format(
                        path=path.child(key_file).path)
        self.assertEqual(str(e), expected)

    @not_root
    @skip_on_broken_permissions
    def test_load_error_on_unreadable_certificate_file(self):
        """
        A ``PathError`` is raised if the certificate file path given to
        ``NodeCredential.from_path`` cannot be opened for reading.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        # random UUID that doesn't exist in path
        uuid = self.uuid
        cert_file = b"{uuid}.crt".format(uuid=uuid)
        key_file = b"{uuid}.key".format(uuid=uuid)
        crt_path = path.child(cert_file)
        crt_file = crt_path.open(b'w')
        crt_file.write(b"dummy")
        crt_file.close()
        # make file unreadable
        crt_path.chmod(0100)
        key_path = path.child(key_file)
        key_file = key_path.open(b'w')
        key_file.write(b"dummy")
        key_file.close()
        # make file unreadable
        key_path.chmod(0100)
        e = self.assertRaises(
            PathError, NodeCredential.from_path, path, uuid
        )
        expected = (
            b"Certificate file could not be opened. "
            b"Permission denied {path}"
        ).format(path=crt_path.path)
        self.assertEqual(str(e), expected)

    @not_root
    @skip_on_broken_permissions
    def test_load_error_on_unreadable_key_file(self):
        """
        A ``PathError`` is raised if the key file path given to
        ``NodeCredential.from_path`` cannot be opened for reading.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        # random UUID that doesn't exist in path
        uuid = self.uuid
        cert_file = b"{uuid}.crt".format(uuid=uuid)
        key_file = b"{uuid}.key".format(uuid=uuid)
        crt_path = path.child(cert_file)
        crt_file = crt_path.open(b'w')
        crt_file.write(b"dummy")
        crt_file.close()
        key_path = path.child(key_file)
        key_file = key_path.open(b'w')
        key_file.write(b"dummy")
        key_file.close()
        # make file unreadable
        key_path.chmod(0100)
        e = self.assertRaises(
            PathError, NodeCredential.from_path, path, uuid
        )
        expected = (
            b"Private key file could not be opened. "
            b"Permission denied {path}"
        ).format(path=key_path.path)
        self.assertEqual(str(e), expected)

    def test_certificate_subject_node_uuid(self):
        """
        A cert written by ``NodeCredential.initialize`` has the
        subject common name "node-{uuid}" where {uuid} is the UUID
        generated during the certificate's creation.
        """
        nc = NodeCredential.initialize(self.path, self.ca)
        cert = nc.credential.certificate.original
        subject = cert.get_subject()
        self.assertEqual(subject.CN, b"node-{uuid}".format(uuid=nc.uuid))

    def test_certificate_ou_matches_ca(self):
        """
        A cert written by ``NodeCredential.initialize`` has the issuing
        authority's common name as its organizational unit name.
        """
        nc = NodeCredential.initialize(self.path, self.ca)
        cert = nc.credential.certificate.original
        issuer = cert.get_issuer()
        subject = cert.get_subject()
        self.assertEqual(
            issuer.CN,
            subject.OU
        )

    def test_certificate_is_signed_by_ca(self):
        """
        A cert written by ``NodeCredential.initialize`` is validated
        as being signed by the certificate authority.
        """
        nc = NodeCredential.initialize(self.path, self.ca)
        cert = nc.credential.certificate.original
        issuer = cert.get_issuer()
        self.assertEqual(
            issuer.CN,
            self.ca.credential.certificate.getSubject().CN
        )

    def test_certificate_expiration(self):
        """
        A cert written by ``NodeCredential.initialize`` has an expiry
        date 20 years from the date of signing.
        """
        today = datetime.datetime.now()
        expected_expiry = today + datetime.timedelta(seconds=EXPIRY_20_YEARS)
        nc = NodeCredential.initialize(self.path, self.ca)
        cert = nc.credential.certificate.original
        asn1 = cert.get_notAfter()
        expiry_date = datetime.datetime.strptime(asn1, "%Y%m%d%H%M%SZ")
        self.assertEqual(expiry_date.date(), expected_expiry.date())

    def test_certificate_is_rsa_4096_sha_256(self):
        """
        A cert written by ``NodeCredential.initialize`` is an RSA
        4096 bit, SHA-256 format.
        """
        nc = NodeCredential.initialize(self.path, self.ca)
        cert = nc.credential.certificate.original
        key = nc.credential.certificate.getPublicKey().original
        self.assertEqual(
            (crypto.TYPE_RSA, 4096, b'sha256WithRSAEncryption'),
            (key.type(), key.bits(), cert.get_signature_algorithm())
        )


class ControlCredentialTests(SynchronousTestCase):
    """
    Tests for ``flocker.ca._ca.ControlCredential``.
    """
    def setUp(self):
        """
        Generate a RootCredential for the control certificate tests
        to work with.
        """
        self.path = FilePath(self.mktemp())
        self.path.makedirs()
        self.ca = RootCredential.initialize(self.path, b"mycluster")

    def test_written_keypair_exists(self):
        """
        ``ControlCredential.initialize`` writes a PEM file to the
        specified path.
        """
        ControlCredential.initialize(self.path, self.ca)
        self.assertEqual(
            (True, True),
            (self.path.child(AUTHORITY_CERTIFICATE_FILENAME).exists(),
             self.path.child(AUTHORITY_KEY_FILENAME).exists())
        )

    def test_decoded_certificate_matches_public_key(self):
        """
        A decoded certificate's public key matches the public key it is
        meant to be paired with.
        """
        cc = ControlCredential.initialize(self.path, self.ca)
        self.assertTrue(
            cc.credential.keypair.keypair.matches(
                cc.credential.certificate.getPublicKey())
        )

    def test_decoded_certificate_matches_private_key(self):
        """
        A decoded certificate matches the private key it is meant to
        be paired with.
        """
        cc = ControlCredential.initialize(self.path, self.ca)
        priv = cc.credential.keypair.keypair.original
        pub = cc.credential.certificate.getPublicKey().original
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
        A keypair written by ``ControlCredential.initialize`` can be
        successfully reloaded in to an identical ``ControlCredential``
        instance.
        """
        cc1 = ControlCredential.initialize(self.path, self.ca)
        cc2 = ControlCredential.from_path(self.path)
        self.assertEqual(cc1, cc2)

    def test_keypair_correct_umask(self):
        """
        A keypair file written by ``ControlCredential.initialize`` has
        the correct permissions (0600).
        """
        ControlCredential.initialize(self.path, self.ca)
        keyPath = self.path.child(CONTROL_KEY_FILENAME)
        st = os.stat(keyPath.path)
        self.assertEqual(b'0600', oct(st.st_mode & 0777))

    def test_certificate_correct_permission(self):
        """
        A certificate file written by ``ControlCredential.initialize`` has
        the correct access mode set (0600).
        """
        ControlCredential.initialize(self.path, self.ca)
        keyPath = self.path.child(CONTROL_CERTIFICATE_FILENAME)
        st = os.stat(keyPath.path)
        self.assertEqual(b'0600', oct(st.st_mode & 0777))

    def test_create_error_on_non_existent_path(self):
        """
        A ``PathError`` is raised if the path given to
        ``ControlCredential.initialize`` does not exist.
        """
        path = FilePath(self.mktemp())
        e = self.assertRaises(
            PathError, ControlCredential.initialize, path, self.ca
        )
        expected = (b"Unable to write certificate file. "
                    b"No such file or directory {path}").format(
                        path=path.child(CONTROL_CERTIFICATE_FILENAME).path)
        self.assertEqual(str(e), expected)

    def test_load_error_on_non_existent_path(self):
        """
        A ``PathError`` is raised if the path given to
        ``ControlCredential.from_path`` does not exist.
        """
        path = FilePath(self.mktemp())
        e = self.assertRaises(
            PathError, ControlCredential.from_path, path
        )
        expected = (b"Certificate file could not be opened. "
                    b"No such file or directory {path}").format(
                        path=path.child(CONTROL_CERTIFICATE_FILENAME).path)
        self.assertEqual(str(e), expected)

    def test_load_error_on_non_existent_certificate_file(self):
        """
        A ``PathError`` is raised if the certificate file path given to
        ``ControlCredential.from_path`` does not exist.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        e = self.assertRaises(
            PathError, ControlCredential.from_path, path
        )
        expected = (b"Certificate file could not be opened. "
                    b"No such file or directory "
                    b"{path}").format(
                        path=path.child(CONTROL_CERTIFICATE_FILENAME).path)
        self.assertEqual(str(e), expected)

    def test_load_error_on_non_existent_key_file(self):
        """
        A ``PathError`` is raised if the key file path given to
        ``ControlCredential.from_path`` does not exist.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        crt_path = path.child(CONTROL_CERTIFICATE_FILENAME)
        crt_file = crt_path.open(b'w')
        crt_file.write(b"dummy")
        crt_file.close()
        e = self.assertRaises(
            PathError, ControlCredential.from_path, path
        )
        expected = (b"Private key file could not be opened. "
                    b"No such file or directory "
                    b"{path}").format(
                        path=path.child(CONTROL_KEY_FILENAME).path)
        self.assertEqual(str(e), expected)

    @not_root
    @skip_on_broken_permissions
    def test_load_error_on_unreadable_certificate_file(self):
        """
        A ``PathError`` is raised if the certificate file path given to
        ``ControlCredential.from_path`` cannot be opened for reading.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        crt_path = path.child(CONTROL_CERTIFICATE_FILENAME)
        crt_file = crt_path.open(b'w')
        crt_file.write(b"dummy")
        crt_file.close()
        # make file unreadable
        crt_path.chmod(0100)
        key_path = path.child(CONTROL_KEY_FILENAME)
        key_file = key_path.open(b'w')
        key_file.write(b"dummy")
        key_file.close()
        # make file unreadable
        key_path.chmod(0100)
        e = self.assertRaises(
            PathError, ControlCredential.from_path, path
        )
        expected = (
            b"Certificate file could not be opened. "
            b"Permission denied {path}"
        ).format(path=crt_path.path)
        self.assertEqual(str(e), expected)

    @not_root
    @skip_on_broken_permissions
    def test_load_error_on_unreadable_key_file(self):
        """
        A ``PathError`` is raised if the key file path given to
        ``ControlCredential.from_path`` cannot be opened for reading.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        crt_path = path.child(CONTROL_CERTIFICATE_FILENAME)
        crt_file = crt_path.open(b'w')
        crt_file.write(b"dummy")
        crt_file.close()
        key_path = path.child(CONTROL_KEY_FILENAME)
        key_file = key_path.open(b'w')
        key_file.write(b"dummy")
        key_file.close()
        # make file unreadable
        key_path.chmod(0100)
        e = self.assertRaises(
            PathError, ControlCredential.from_path, path
        )
        expected = (
            b"Private key file could not be opened. "
            b"Permission denied {path}"
        ).format(path=key_path.path)
        self.assertEqual(str(e), expected)

    def test_certificate_subject_control_service(self):
        """
        A cert written by ``ControlCredential.initialize`` has the
        subject common name "control-service"
        """
        cc = ControlCredential.initialize(self.path, self.ca)
        cert = cc.credential.certificate.original
        subject = cert.get_subject()
        self.assertEqual(subject.CN, b"control-service")

    def test_certificate_ou_matches_ca(self):
        """
        A cert written by ``ControlCredential.initialize`` has the issuing
        authority's common name as its organizational unit name.
        """
        cc = ControlCredential.initialize(self.path, self.ca)
        cert = cc.credential.certificate.original
        issuer = cert.get_issuer()
        subject = cert.get_subject()
        self.assertEqual(
            issuer.CN,
            subject.OU
        )

    def test_certificate_is_signed_by_ca(self):
        """
        A cert written by ``ControlCredential.initialize`` is validated
        as being signed by the certificate authority.
        """
        cc = ControlCredential.initialize(self.path, self.ca)
        cert = cc.credential.certificate.original
        issuer = cert.get_issuer()
        self.assertEqual(
            issuer.CN,
            self.ca.credential.certificate.getSubject().CN
        )

    def test_certificate_expiration(self):
        """
        A cert written by ``ControlCredential.initialize`` has an expiry
        date 20 years from the date of signing.
        """
        today = datetime.datetime.now()
        expected_expiry = today + datetime.timedelta(seconds=EXPIRY_20_YEARS)
        cc = ControlCredential.initialize(self.path, self.ca)
        cert = cc.credential.certificate.original
        asn1 = cert.get_notAfter()
        expiry_date = datetime.datetime.strptime(asn1, "%Y%m%d%H%M%SZ")
        self.assertEqual(expiry_date.date(), expected_expiry.date())

    def test_certificate_is_rsa_4096_sha_256(self):
        """
        A cert written by ``ControlCredential.initialize`` is an RSA
        4096 bit, SHA-256 format.
        """
        cc = ControlCredential.initialize(self.path, self.ca)
        cert = cc.credential.certificate.original
        key = cc.credential.certificate.getPublicKey().original
        self.assertEqual(
            (crypto.TYPE_RSA, 4096, b'sha256WithRSAEncryption'),
            (key.type(), key.bits(), cert.get_signature_algorithm())
        )


class RootCredentialTests(SynchronousTestCase):
    """
    Tests for ``flocker.ca._ca.RootCredential``.
    """
    def test_written_keypair_exists(self):
        """
        ``RootCredential.initialize`` writes a PEM file to the
        specified path.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        RootCredential.initialize(path, b"mycluster")
        self.assertEqual(
            (True, True),
            (path.child(AUTHORITY_CERTIFICATE_FILENAME).exists(),
             path.child(AUTHORITY_KEY_FILENAME).exists())
        )

    def test_decoded_certificate_matches_public_key(self):
        """
        A decoded certificate's public key matches the public key it is
        meant to be paired with.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        ca = RootCredential.initialize(path, b"mycluster")
        self.assertTrue(
            ca.credential.keypair.keypair.matches(
                ca.credential.certificate.getPublicKey())
        )

    def test_decoded_certificate_matches_private_key(self):
        """
        A decoded certificate matches the private key it is meant to
        be paired with.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        ca = RootCredential.initialize(path, b"mycluster")
        priv = ca.credential.keypair.keypair.original
        pub = ca.credential.certificate.getPublicKey().original
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
        A keypair written by ``RootCredential.initialize`` can be
        successfully reloaded in to an identical ``RootCredential``
        instance.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        ca1 = RootCredential.initialize(path, b"mycluster")
        ca2 = RootCredential.from_path(path)
        self.assertEqual(ca1, ca2)

    def test_keypair_correct_umask(self):
        """
        A keypair file written by ``RootCredential.initialize`` has
        the correct permissions (0600).
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        RootCredential.initialize(path, b"mycluster")
        keyPath = path.child(AUTHORITY_KEY_FILENAME)
        st = os.stat(keyPath.path)
        self.assertEqual(b'0600', oct(st.st_mode & 0777))

    def test_certificate_correct_permission(self):
        """
        A certificate file written by ``RootCredential.initialize`` has
        the correct access mode set (0600).
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        RootCredential.initialize(path, b"mycluster")
        keyPath = path.child(AUTHORITY_CERTIFICATE_FILENAME)
        st = os.stat(keyPath.path)
        self.assertEqual(b'0600', oct(st.st_mode & 0777))

    def test_create_error_on_non_existent_path(self):
        """
        A ``PathError`` is raised if the path given to
        ``RootCredential.initialize`` does not exist.
        """
        path = FilePath(self.mktemp())
        e = self.assertRaises(
            PathError, RootCredential.initialize, path, b"mycluster"
        )
        expected = (b"Unable to write certificate file. "
                    b"No such file or directory "
                    b"{path}").format(path=path.child(
                        AUTHORITY_CERTIFICATE_FILENAME).path)
        self.assertEqual(str(e), expected)

    def test_load_error_on_non_existent_path(self):
        """
        A ``PathError`` is raised if the path given to
        ``RootCredential.from_path`` does not exist.
        """
        path = FilePath(self.mktemp())
        e = self.assertRaises(
            PathError, RootCredential.from_path, path
        )
        expected = (
            b"Unable to load certificate authority file. Please run "
            b"`flocker-ca initialize` to generate a new certificate "
            b"authority. No such file or directory {path}"
        ).format(path=path.child(AUTHORITY_CERTIFICATE_FILENAME).path)
        self.assertEqual(str(e), expected)

    def test_load_error_on_non_existent_certificate_file(self):
        """
        A ``PathError`` is raised if the certificate file path given to
        ``RootCredential.from_path`` does not exist.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        e = self.assertRaises(
            PathError, RootCredential.from_path, path
        )
        expected = (
            b"Unable to load certificate authority file. Please run "
            b"`flocker-ca initialize` to generate a new certificate "
            b"authority. No such file or directory {path}"
        ).format(path=path.child(AUTHORITY_CERTIFICATE_FILENAME).path)
        self.assertEqual(str(e), expected)

    def test_load_error_on_non_existent_key_file(self):
        """
        A ``PathError`` is raised if the key file path given to
        ``RootCredential.from_path`` does not exist.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        crt_path = path.child(AUTHORITY_CERTIFICATE_FILENAME)
        crt_file = crt_path.open(b'w')
        crt_file.write(b"dummy")
        crt_file.close()
        e = self.assertRaises(
            PathError, RootCredential.from_path, path
        )
        expected = (
            b"Unable to load certificate authority file. Please run "
            b"`flocker-ca initialize` to generate a new certificate "
            b"authority. No such file or directory {path}"
        ).format(path=path.child(AUTHORITY_KEY_FILENAME).path)
        self.assertEqual(str(e), expected)

    @not_root
    @skip_on_broken_permissions
    def test_load_error_on_unreadable_certificate_file(self):
        """
        A ``PathError`` is raised if the certificate file path given to
        ``RootCredential.from_path`` cannot be opened for reading.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        crt_path = path.child(AUTHORITY_CERTIFICATE_FILENAME)
        crt_file = crt_path.open(b'w')
        crt_file.write(b"dummy")
        crt_file.close()
        # make file unreadable
        crt_path.chmod(0100)
        key_path = path.child(AUTHORITY_KEY_FILENAME)
        key_file = key_path.open(b'w')
        key_file.write(b"dummy")
        key_file.close()
        # make file unreadable
        key_path.chmod(0100)
        e = self.assertRaises(
            PathError, RootCredential.from_path, path
        )
        expected = (
            b"Unable to load certificate authority file. "
            b"Permission denied {path}"
        ).format(path=crt_path.path)
        self.assertEqual(str(e), expected)

    @not_root
    @skip_on_broken_permissions
    def test_load_error_on_unreadable_key_file(self):
        """
        A ``PathError`` is raised if the key file path given to
        ``RootCredential.from_path`` cannot be opened for reading.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        crt_path = path.child(AUTHORITY_CERTIFICATE_FILENAME)
        crt_file = crt_path.open(b'w')
        crt_file.write(b"dummy")
        crt_file.close()
        key_path = path.child(AUTHORITY_KEY_FILENAME)
        key_file = key_path.open(b'w')
        key_file.write(b"dummy")
        key_file.close()
        # make file unreadable
        key_path.chmod(0100)
        e = self.assertRaises(
            PathError, RootCredential.from_path, path
        )
        expected = (
            b"Unable to load certificate authority file. "
            b"Permission denied {path}"
        ).format(path=key_path.path)
        self.assertEqual(str(e), expected)

    def test_certificate_is_self_signed(self):
        """
        A cert written by ``RootCredential.initialize`` is validated
        as a self-signed certificate.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        ca = RootCredential.initialize(path, b"mycluster")
        cert = ca.credential.certificate.original
        issuer = cert.get_issuer().get_components()
        subject = cert.get_subject().get_components()
        self.assertEqual(issuer, subject)

    def test_certificate_expiration(self):
        """
        A cert written by ``RootCredential.initialize`` has an expiry
        date 20 years from the date of signing.
        """
        today = datetime.datetime.now()
        expected_expiry = today + datetime.timedelta(seconds=EXPIRY_20_YEARS)
        path = FilePath(self.mktemp())
        path.makedirs()
        ca = RootCredential.initialize(path, b"mycluster")
        cert = ca.credential.certificate.original
        asn1 = cert.get_notAfter()
        expiry_date = datetime.datetime.strptime(asn1, "%Y%m%d%H%M%SZ")
        self.assertEqual(expiry_date.date(), expected_expiry.date())

    def test_certificate_is_rsa_4096_sha_256(self):
        """
        A cert written by ``RootCredential.initialize`` is an RSA
        4096 bit, SHA-256 format.
        """
        path = FilePath(self.mktemp())
        path.makedirs()
        ca = RootCredential.initialize(path, b"mycluster")
        cert = ca.credential.certificate.original
        key = ca.credential.certificate.getPublicKey().original
        self.assertEqual(
            (crypto.TYPE_RSA, 4096, b'sha256WithRSAEncryption'),
            (key.type(), key.bits(), cert.get_signature_algorithm())
        )
