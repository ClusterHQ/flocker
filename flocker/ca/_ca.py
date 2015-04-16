# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Low-level logic for a certificate authority.

Uses RSA 4096-bit + SHA 256.
"""

import os

from uuid import uuid4

from OpenSSL import crypto
from pyrsistent import PRecord, field
from twisted.internet.ssl import DistinguishedName, KeyPair, Certificate


EXPIRY_20_YEARS = 60 * 60 * 24 * 365 * 20

authority_certificate_filename = b"cluster.crt"
authority_key_filename = b"cluster.key"
control_certificate_filename = b"control-service.crt"
control_key_filename = b"control-service.key"


class CertificateAlreadyExistsError(Exception):
    """
    Error raised when a certificate file already exists.
    """


class KeyAlreadyExistsError(Exception):
    """
    Error raised when a keypair file already exists.
    """


class PathError(Exception):
    """
    Error raised when the directory for certificate files does not exist.
    """


class FlockerKeyPair(object):
    """
    KeyPair with added functionality for comparison and signing a request
    object with additional extensions for generating a self-signed CA.

    Written in Twisted-style as these changes should be upstreamed to
    ``twisted.internet.ssl.KeyPair``

    https://twistedmatrix.com/trac/ticket/7847
    """
    def __init__(self, keypair):
        self.keypair = keypair

    def __eq__(self, other):
        if isinstance(other, FlockerKeyPair):
            return self.keypair.dump() == other.keypair.dump()
        return False

    def __ne__(self, other):
        return not self.__eq__(other)

    @classmethod
    def generate(cls):
        """
        Create a new 4096-bit RSA key pair.
        """
        return cls(
            keypair=KeyPair.generate(crypto.TYPE_RSA, size=4096)
        )

    def selfSignedCACertificate(self, dn, request, serial, expiry, digest):
        """
        Sign a CertificateRequest with extensions for use as a CA certificate.

        See
        https://www.openssl.org/docs/apps/x509v3_config.html#Basic-Constraints
        for further information.

        This code based on ``twisted.internet.ssl.KeyPair.signRequestObject``

        :param DistinguishedName dn: The ``DistinguishedName`` for the
            certificate.

        :param CertificateRequest request: The signing request object.

        :param int serial: The certificate serial number.

        :param int expiry: Number of seconds from now until this certificate
            should expire.

        :param str digest: The digest algorithm to use.
        """
        req = request.original
        cert = crypto.X509()
        dn._copyInto(cert.get_issuer())
        cert.set_subject(req.get_subject())
        cert.set_pubkey(req.get_pubkey())
        cert.gmtime_adj_notBefore(0)
        cert.gmtime_adj_notAfter(expiry)
        cert.set_serial_number(serial)
        cert.add_extensions([
            crypto.X509Extension("basicConstraints", True,
                                 "CA:TRUE, pathlen:0"),
            crypto.X509Extension("keyUsage", True,
                                 "keyCertSign, cRLSign"),
            crypto.X509Extension("subjectKeyIdentifier", False, "hash",
                                 subject=cert),
        ])
        cert.add_extensions([
            crypto.X509Extension(
                "authorityKeyIdentifier", False,
                "keyid:always", issuer=cert
            )
        ])
        cert.sign(self.keypair.original, digest)
        return Certificate(cert)


def load_certificate_from_path(path, key_filename, cert_filename):
    """
    Load a certificate and keypair from a specified path.

    :param FilePath path: Directory where certificate and key files
        are stored.
    :param bytes key_filename: The file name of the private key.
    :param bytes cert_filename: The file name of the certificate.

    :return: A ``tuple`` containing the loaded key and certificate
        instances.
    """
    if not path.isdir():
        raise PathError(
            b"Path {path} is not a directory.".format(path=path.path)
        )

    certPath = path.child(cert_filename)
    keyPath = path.child(key_filename)

    if not certPath.isfile():
        raise PathError(
            b"Certificate file {path} does not exist.".format(
                path=certPath.path)
        )

    if not keyPath.isfile():
        raise PathError(
            b"Private key file {path} does not exist.".format(
                path=keyPath.path)
        )

    try:
        certFile = certPath.open()
    except IOError:
        raise PathError(
            (b"Certificate file {path} could not be opened. "
             b"Check file permissions.").format(
                path=certPath.path)
        )

    try:
        keyFile = keyPath.open()
    except IOError:
        raise PathError(
            (b"Private key file {path} could not be opened. "
             b"Check file permissions.").format(
                path=keyPath.path)
        )

    certificate = Certificate.load(
        certFile.read(), format=crypto.FILETYPE_PEM)
    keypair = FlockerKeyPair(
        keypair=KeyPair.load(keyFile.read(), format=crypto.FILETYPE_PEM)
    )
    return (keypair, certificate)


class FlockerCertificate(PRecord):
    """
    Base class for Flocker certificates.

    :ivar FilePath path: A ``FilePath`` representing the absolute path of
        a directory containing the certificate and key files.
    :ivar Certificate certificate: A signed certificate, populated only by
        loading from ``path``.
    :ivar FlockerKeyPair keypair: A private/public keypair, populated only by
        loading from ``path``.
    """
    path = field(mandatory=True)
    certificate = field(mandatory=True, initial=None)
    keypair = field(mandatory=True, initial=None)

    @classmethod
    def from_path(path):
        return cls(
            path=path, keypair=keypair, certificate=certificate
        )


class ControlCertificate(FlockerCertificate):
    """
    A certificate for a control service, signed by a supplied certificate
    authority.

    :ivar FilePath path: A ``FilePath`` representing the absolute path of
        a directory containing the certificate and key files.
    :ivar Certificate certificate: A signed certificate, populated only by
        loading from ``path``.
    :ivar FlockerKeyPair keypair: A private/public keypair, populated only by
        loading from ``path``.
    """
    path = field(mandatory=True)
    certificate = field(mandatory=True, initial=None)
    keypair = field(mandatory=True, initial=None)

    @classmethod
    def from_path(cls, path):
        keypair, certificate = load_certificate_from_path(
            path, control_key_filename, control_certificate_filename
        )
        return cls(
            path=path, keypair=keypair, certificate=certificate
        )

    @classmethod
    def initialize(cls, authority, path):
        """
        Generate a certificate signed by the supplied root certificate.

        :param CertificateAuthority authority: The certificate authority with
            which this certificate will be signed.
        :param FilePath path: Directory where the certificate will be stored.
        """
        if not path.isdir():
            raise PathError(
                b"Path {path} is not a directory.".format(path=path.path)
            )

        certPath = path.child(control_certificate_filename)
        keyPath = path.child(control_key_filename)

        if certPath.exists():
            raise CertificateAlreadyExistsError(
                b"Certificate file {path} already exists.".format(
                    path=certPath.path)
            )
        if keyPath.exists():
            raise KeyAlreadyExistsError(
                b"Private key file {path} already exists.".format(
                    path=keyPath.path)
            )

        # The common name for the control service certificate.
        # This is used to distinguish between control service and node
        # certificates.
        name = b"control-service"
        # The organizational unit is set to the common name of the
        # authority, which in our case is a byte string identifying
        # the cluster.
        organizational_unit = authority.certificate.getSubject().CN
        dn = DistinguishedName(
            commonName=name, organizationalUnitName=organizational_unit
        )
        keypair = FlockerKeyPair.generate()
        request = keypair.keypair.requestObject(dn)
        serial = os.urandom(16).encode(b"hex")
        serial = int(serial, 16)
        cert = authority.keypair.keypair.signRequestObject(
            authority.certificate.getSubject(), request,
            serial, EXPIRY_20_YEARS, 'sha256'
        )
        original_umask = os.umask(0)
        mode = 0o600
        with os.fdopen(os.open(
            certPath.path, os.O_WRONLY | os.O_CREAT, mode
        ), b'w') as certFile:
            certFile.write(cert.dumpPEM())
        with os.fdopen(os.open(
            keyPath.path, os.O_WRONLY | os.O_CREAT, mode
        ), b'w') as keyFile:
            keyFile.write(keypair.keypair.dump(crypto.FILETYPE_PEM))
        os.umask(original_umask)
        return cls.from_path(
            path, (control_certificate_filename, control_key_filename)
        )


class CertificateAuthority(FlockerCertificate):
    """
    A self-signed certificate authority.

    :ivar FilePath path: A ``FilePath`` representing the absolute path of
        a directory containing the certificate and key files.
    :ivar Certificate certificate: A signed certificate, populated only by
        loading from ``path``.
    :ivar FlockerKeyPair keypair: A private/public keypair, populated only by
        loading from ``path``.
    """
    path = field(mandatory=True)
    certificate = field(mandatory=True, initial=None)
    keypair = field(mandatory=True, initial=None)

    @classmethod
    def from_path(cls, path):
        keypair, certificate = load_certificate_from_path(
            path, authority_key_filename, authority_certificate_filename
        )
        return cls(
            path=path, keypair=keypair, certificate=certificate
        )

    @classmethod
    def initialize(cls, path, name):
        """
        Generate new private/public key pair and self-sign, then store in
        given directory.

        :param FilePath path: Directory where private key and certificate are
            stored.
        :param bytes name: The name of the cluster. This is used as the
            subject and issuer identities of the generated root certificate.

        :return CertificateAuthority: Initialized certificate authority.
        """
        if not path.isdir():
            raise PathError(
                b"Path {path} is not a directory.".format(path=path.path)
            )

        certPath = path.child(authority_certificate_filename)
        keyPath = path.child(authority_key_filename)

        if certPath.exists():
            raise CertificateAlreadyExistsError(
                b"Certificate file {path} already exists.".format(
                    path=certPath.path)
            )
        if keyPath.exists():
            raise KeyAlreadyExistsError(
                b"Private key file {path} already exists.".format(
                    path=keyPath.path)
            )

        dn = DistinguishedName(commonName=name)
        keypair = FlockerKeyPair.generate()
        request = keypair.keypair.requestObject(dn)
        serial = os.urandom(16).encode(b"hex")
        serial = int(serial, 16)
        certificate = keypair.selfSignedCACertificate(
            dn, request, serial, EXPIRY_20_YEARS, 'sha256'
        )
        original_umask = os.umask(0)
        mode = 0o600
        with os.fdopen(os.open(
            certPath.path, os.O_WRONLY | os.O_CREAT, mode
        ), b'w') as certFile:
            certFile.write(certificate.dumpPEM())
        with os.fdopen(os.open(
            keyPath.path, os.O_WRONLY | os.O_CREAT, mode
        ), b'w') as keyFile:
            keyFile.write(keypair.keypair.dump(crypto.FILETYPE_PEM))
        os.umask(original_umask)
        return cls.from_path(path)
