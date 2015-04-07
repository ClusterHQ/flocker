# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Low-level logic for a certificate authority.

Uses ECDSA + SHA256? Or if that turns out to be too difficult RSA 4096-bit
+ SHA 256.
"""

import os

from OpenSSL import crypto
from pyrsistent import PRecord, field
from twisted.internet.ssl import DistinguishedName, KeyPair, Certificate


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
    XXX Twisted's ``KeyPair``s are not comparable so this class wraps it
    to provide comparison.
    """
    def __init__(self, keypair):
        self.keypair = keypair

    def __eq__(self, other):
        if isinstance(other, FlockerKeyPair):
            return self.keypair.dump() == other.keypair.dump()
        return False

    def __ne__(self, other):
        return not self.__eq__(other)


def generate_keypair():
    """
    Create a new key pair.
    """
    return FlockerKeyPair(
        keypair=KeyPair.generate(crypto.TYPE_RSA, size=4096)
    )


class CertificateAuthority(PRecord):
    """
    A certificate authority whose configuration is stored in a specified
    directory.

    :ivar FilePath path: A ``FilePath`` representing the absolute path of
        a directory containing the CRT and KEY files.
    :ivar Certificate certificate: A signed certificate, populated only by
        loading from path.
    :ivar FlockerKeyPair keypair: A private/public keypair, populated only by
        loading from path.
    """
    certificate = field(mandatory=True, initial=None)
    keypair = field(mandatory=True, initial=None)
    path = field(mandatory=True)

    @classmethod
    def from_path(cls, path):
        """
        :param FilePath path: Directory where private key and certificate are
            stored.
        """
        if not path.isdir():
            raise PathDoesNotExistError(
                b"Path {path} is not a directory.".format(path=path.path)
            )

        certPath = path.child("cluster.crt")
        keyPath = path.child("cluster.key")

        if not certPath.isfile():
            raise PathError(
                b"Certificate file {path} does not exist.".format(
                    path=certPath.path)
            )

        if not keyPath.isfile():
            raise PathError(
                b"Private key file {path} does not exist.".format(
                    path=certPath.path)
            )

        try:
            certFile = certPath.open()
        except IOError as e:
            raise PathError(
                (b"Certificate file {path} could not be opened. "
                 b"Check file permissions.").format(
                    path=certPath.path)
            )

        try:
            keyFile = keyPath.open()
        except IOError as e:
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

        return cls(path=path, certificate=certificate, keypair=keypair)

    @classmethod
    def initialize(cls, path, name):
        """
        Generate new private/public key pair and self-sign, then store in
        given directory.

        :param FilePath path: Directory where private key and certificate are
            stored.
        :param bytes name: The name of the cluster.

        :return CertificateAuthority: Initialized certificate authority.
        """
        EXPIRY_20_YEARS = 60 * 60 * 24 * 365 * 20

        if not path.isdir():
            raise PathError(
                b"Path {path} is not a directory.".format(path=path.path)
            )

        certPath = path.child("cluster.crt")
        keyPath = path.child("cluster.key")

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
        keypair = generate_keypair()
        request = keypair.keypair.requestObject(dn)
        serial = os.urandom(16).encode(b"hex")
        serial = int(serial, 16)
        certificate = keypair.keypair.signRequestObject(
            dn, request, serial,
            secondsToExpiry=EXPIRY_20_YEARS,
            digestAlgorithm='sha256'
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
