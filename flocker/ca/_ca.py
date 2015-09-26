# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Low-level logic for a certificate authority.

We have three categories of certificates:

1. Control service, used by AMP and REST API servers. Needs to be
   validated over HTTP by 3rd party clients, as well as by AMP clients.
2. Node agents, used by AMP clients in agents. Needs to encode a node
   UUID, and is validated by the control service.
3. API clients. Used by HTTP API clients to authenticate, so the control
   service REST API needs to validate them.

None of these should be able to impersonate the others. We therefore use
the following Distinguised Name scheme:

1. Control service: common name is "control-service", subjectAltName is
   administrator-specifiable DNS hostname, to support standard HTTPS
   client authentication.
2. Node agents: common name is "node-<uuid>".
3. API clients: Common name is set to "user-<username>", and
   extendedKeyUsage is set to "clientAuth" (under no circumstances should
   a client certificate ever be a server.)

It would be nice to use a custom x509v3 extension rather than abusing the
common name, but that will have to wait for some future revision.
"""

import datetime
import os

from uuid import uuid4, UUID

from ipaddr import IPAddress
from OpenSSL import crypto
from pyrsistent import PRecord, field
from twisted.internet.ssl import (
    DistinguishedName, KeyPair, Certificate, CertificateOptions,
    PrivateCertificate,
)


EXPIRY_20_YEARS = 60 * 60 * 24 * 365 * 20

AUTHORITY_CERTIFICATE_FILENAME = b"cluster.crt"
AUTHORITY_KEY_FILENAME = b"cluster.key"


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
    def __init__(self, message, filename=None, code=None, failure=None):
        super(PathError, self).__init__(message)
        self.filename = filename
        self.code = code
        self.failure = failure

    def __str__(self):
        error = self.message
        if self.failure:
            error = error + b" " + self.failure
        if self.filename:
            error = error + b" " + self.filename
        return error


class ComparableKeyPair(object):
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
        if isinstance(other, ComparableKeyPair):
            return self.keypair.dump() == other.keypair.dump()
        return False

    def __ne__(self, other):
        return not self.__eq__(other)


def create_certificate_authority(keypair, dn, request, serial,
                                 validity_period, digest, start=None):
    """
    Sign a CertificateRequest with extensions for use as a CA certificate.

    See
    https://www.openssl.org/docs/apps/x509v3_config.html#Basic-Constraints
    for further information.

    This code based on ``twisted.internet.ssl.KeyPair.signRequestObject``

    :param KeyPair keypair: The private/public key pair.

    :param DistinguishedName dn: The ``DistinguishedName`` for the
        certificate.

    :param CertificateRequest request: The signing request object.

    :param int serial: The certificate serial number.

    :param int validity_period: The number of seconds from ``start`` after
        which the certificate expires.

    :param bytes digest: The digest algorithm to use.

    :param datetime start: The datetime from which the certificate is valid.
        Defaults to current date and time.
    """
    if start is None:
        start = datetime.datetime.utcnow()
    expire = start + datetime.timedelta(seconds=validity_period)
    start = start.strftime(b"%Y%m%d%H%M%SZ")
    expire = expire.strftime(b"%Y%m%d%H%M%SZ")
    req = request.original
    cert = crypto.X509()
    cert.set_subject(req.get_subject())
    cert.set_pubkey(req.get_pubkey())
    cert.set_notBefore(start)
    cert.set_notAfter(expire)
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
    cert.set_issuer(cert.get_subject())
    cert.sign(keypair.original, digest)
    return Certificate(cert)


def sign_certificate_request(keypair, dn, request, serial,
                             validity_period, digest, start=None,
                             additional_extensions=()):
    """
    Sign a CertificateRequest and return a Certificate.

    This code based on ``twisted.internet.ssl.KeyPair.signRequestObject``

    :param KeyPair keypair: The private/public key pair.

    :param X509Name dn: The distinguished name for the
        certificate.

    :param CertificateRequest request: The signing request object.

    :param int serial: The certificate serial number.

    :param int validity_period: The number of seconds from ``start`` after
        which the certificate expires.

    :param bytes digest: The digest algorithm to use.

    :param datetime start: The datetime from which the certificate is valid.
        Defaults to current date and time.

    :param additional_extensions: A sequence of additional
         ``X509Extension`` objects to add to the certificate.
    """
    if start is None:
        start = datetime.datetime.utcnow()
    expire = start + datetime.timedelta(seconds=validity_period)
    start = start.strftime(b"%Y%m%d%H%M%SZ")
    expire = expire.strftime(b"%Y%m%d%H%M%SZ")
    req = request.original
    cert = crypto.X509()
    cert.set_issuer(dn)
    cert.set_subject(req.get_subject())
    cert.set_pubkey(req.get_pubkey())
    cert.set_notBefore(start)
    cert.set_notAfter(expire)
    cert.set_serial_number(serial)
    cert.add_extensions(additional_extensions)
    cert.sign(keypair.original, digest)
    return Certificate(cert)


def flocker_keypair():
    """
    Create a new 4096-bit RSA key pair.
    """
    return ComparableKeyPair(
        keypair=KeyPair.generate(crypto.TYPE_RSA, size=4096)
    )


def load_certificate_file(path):
    """
    Load a certificate from a specified path.

    :param FilePath path: Absolute path to certificate file.

    :return: A ``Certificate`` instance representing the parsed
        certificate data.
    """
    try:
        certificate_file = path.open()
    except IOError as e:
        code, failure = e
        raise PathError(
            b"Certificate file could not be opened.",
            e.filename, code, failure
        )
    certificate = Certificate.load(
        certificate_file.read(), format=crypto.FILETYPE_PEM)
    return certificate


def load_key_file(path):
    """
    Load a private key from a specified path.

    :param FilePath path: Absolute path to certificate file.

    :return: A ``ComparableKeyPair`` instance representing the parsed
        key data.
    """
    try:
        key_file = path.open()
    except IOError as e:
        code, failure = e
        raise PathError(
            b"Private key file could not be opened.",
            e.filename, code, failure
        )
    keypair = ComparableKeyPair(
        keypair=KeyPair.load(key_file.read(), format=crypto.FILETYPE_PEM)
    )
    return keypair


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
    cert_path = path.child(cert_filename)
    key_path = path.child(key_filename)
    certificate = load_certificate_file(cert_path)
    keypair = load_key_file(key_path)
    return (keypair, certificate)


class FlockerCredential(PRecord):
    """
    Flocker credentials record, comprising a certificate and
    public/private key pair.

    :ivar FilePath path: A ``FilePath`` representing the absolute path of
        a directory containing the certificate and key files.
    :ivar Certificate certificate: A signed certificate.
    :ivar ComparableKeyPair keypair: A private/public keypair.
    """
    path = field(mandatory=True)
    certificate = field(mandatory=True)
    keypair = field(mandatory=True)

    def write_credential_files(self, key_filename, certificate_filename):
        """
        Write PEM encoded certificate and private key files for this credential
        instance.

        :param bytes key_filename: The name of the private key file to write,
            e.g. "cluster.key"
        :param bytes certificate_filename: The name of the certificate file to
            write, e.g. "cluster.crt"
        """
        key_path = self.path.child(key_filename)
        cert_path = self.path.child(certificate_filename)
        original_umask = os.umask(0)
        mode = 0o600
        try:
            with os.fdopen(os.open(
                cert_path.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode
            ), b'w') as cert_file:
                cert_file.write(self.certificate.dumpPEM())
            try:
                with os.fdopen(os.open(
                    key_path.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode
                ), b'w') as key_file:
                    key_file.write(
                        self.keypair.keypair.dump(crypto.FILETYPE_PEM))
            except (IOError, OSError) as e:
                code, failure = e
                raise PathError(
                    b"Unable to write private key file.",
                    e.filename, code, failure
                )
        except (IOError, OSError) as e:
            code, failure = e
            raise PathError(
                b"Unable to write certificate file.",
                e.filename, code, failure
            )
        finally:
            os.umask(original_umask)

    def private_certificate(self):
        """
        Combine private key and certificate into a ``PrivateCertificate``.

        :return: ``PrivateCertificate`` instance.
        """
        return PrivateCertificate.fromCertificateAndKeyPair(
            self.certificate, self.keypair.keypair)


class UserCredential(PRecord):
    """
    A certificate for an API user, signed by a supplied certificate
    authority.

    :ivar FlockerCredential credential: The certificate and key pair
        credential object.
    :ivar bytes username: A username.
    """
    credential = field(mandatory=True, type=FlockerCredential)
    username = field(mandatory=True, type=unicode)

    @classmethod
    def from_files(cls, certificate_path, key_path):
        """
        Load a user certificate and keypair from the specified file paths.
        Extracts the username from the parsed certificate.

        :param FilePath certificate_path: Absolute path to the user
            certificate file.
        :param FilePath key_path: Absolute path to the user private key file.

        :return: A ``UserCredential`` instance representing the parsed data.
        """
        certificate = load_certificate_file(certificate_path)
        keypair = load_key_file(key_path)
        dn = certificate.getSubject()
        # Convert the common name to a string and remove the "user-" prefix
        # to extract the actual username.
        username = dn.CN.decode("utf-8").replace(u"user-", u"", 1)
        # We have no need for the ``path`` attribute on FlockerCredential
        # except when we write the files, so for now we can set this to the
        # directory of the certificate path.
        # FlockerCredential should be modified to not work like this though.
        # See FLOC-2414
        credential = FlockerCredential(
            path=certificate_path.parent(),
            keypair=keypair,
            certificate=certificate
        )
        return cls(credential=credential, username=username)

    @classmethod
    def from_path(cls, path, username):
        """
        Load a user certificate from a specified directory path.

        :param FilePath path: Directory where user certificate and key
            files are stored.
        :param unicode username: The UTF-8 encoded username.
        """
        key_filename = username + u".key"
        cert_filename = username + u".crt"
        keypair, certificate = load_certificate_from_path(
            path, key_filename, cert_filename
        )
        credential = FlockerCredential(
            path=path, keypair=keypair, certificate=certificate)
        return cls(credential=credential, username=username)

    @classmethod
    def initialize(cls, output_path, authority, username, begin=None):
        """
        Generate a certificate signed by the supplied root certificate.

        :param FilePath output_path: Directory where the certificate will be
            written.
        :param CertificateAuthority authority: The certificate authority with
            which this certificate will be signed.
        :param unicode username: A UTF-8 encoded username to be included in
            the certificate.
        :param datetime begin: The datetime from which the generated
            certificate should be valid.
        """
        key_filename = username + u".key"
        cert_filename = username + u".crt"
        # The common name for the node certificate.
        name = u"user-" + username
        # The organizational unit is set to the common name of the
        # authority, which in our case is a byte string identifying
        # the cluster.
        organizational_unit = authority.organizational_unit
        dn = DistinguishedName(
            commonName=name, organizationalUnitName=organizational_unit
        )
        keypair = flocker_keypair()
        request = keypair.keypair.requestObject(dn)
        serial = os.urandom(16).encode(b"hex")
        serial = int(serial, 16)
        cert = sign_certificate_request(
            authority.credential.keypair.keypair,
            authority.credential.certificate.original.get_subject(), request,
            serial, EXPIRY_20_YEARS, b'sha256', start=begin,
            additional_extensions=[crypto.X509Extension(
                b"extendedKeyUsage", False, b"clientAuth")])
        credential = FlockerCredential(
            path=output_path, keypair=keypair, certificate=cert
        )
        credential.write_credential_files(key_filename, cert_filename)
        instance = cls(credential=credential, username=username)
        return instance


class NodeCredential(PRecord):
    """
    A certificate for a node agent, signed by a supplied certificate
    authority.

    :ivar FlockerCredential credential: The certificate and key pair
        credential object.
    :ivar UUID uuid: A unique identifier for the node this certificate
        identifies, in the form of a version 4 UUID.
    :ivar UUID cluster_uuid: A unique identifier for the cluster this
        certificate identifies, in the form of a version 4 UUID.
    """
    credential = field(mandatory=True)

    # The prefix to the UUID we store in the common name:
    _UUID_PREFIX = b"node-"

    @classmethod
    def from_path(cls, path, uuid):
        """
        Load a node certificate from a specified path.

        :param FilePath path: Directory where user certificate and key
            files are stored.
        :param bytes uuid: The UUID of the node.

        """
        key_filename = b"{uuid}.key".format(uuid=uuid)
        cert_filename = b"{uuid}.crt".format(uuid=uuid)
        keypair, certificate = load_certificate_from_path(
            path, key_filename, cert_filename
        )
        credential = FlockerCredential(
            path=path, keypair=keypair, certificate=certificate)
        return cls(credential=credential)

    @classmethod
    def initialize(cls, path, authority, begin=None, uuid=None):
        """
        Generate a certificate signed by the supplied root certificate.

        :param FilePath path: Directory where the certificate will be stored.
        :param CertificateAuthority authority: The certificate authority with
            which this certificate will be signed.
        :param datetime begin: The datetime from which the generated
            certificate should be valid.
        :param bytes uuid: The UUID to be included in this certificate.
            Generated if not supplied.
        """
        if uuid is None:
            uuid = bytes(uuid4())
        key_filename = b"{uuid}.key".format(uuid=uuid)
        cert_filename = b"{uuid}.crt".format(uuid=uuid)
        # The common name for the node certificate.
        name = b"{prefix}{uuid}".format(prefix=cls._UUID_PREFIX, uuid=uuid)
        # The organizational unit is set to the organizational unit of the
        # authority, which in our case is cluster's UUID.
        organizational_unit = authority.organizational_unit
        dn = DistinguishedName(
            commonName=name, organizationalUnitName=organizational_unit
        )
        keypair = flocker_keypair()
        request = keypair.keypair.requestObject(dn)
        serial = os.urandom(16).encode(b"hex")
        serial = int(serial, 16)
        cert = sign_certificate_request(
            authority.credential.keypair.keypair,
            authority.credential.certificate.original.get_subject(), request,
            serial, EXPIRY_20_YEARS, 'sha256', start=begin)
        credential = FlockerCredential(
            path=path, keypair=keypair, certificate=cert)
        credential.write_credential_files(
            key_filename, cert_filename)
        instance = cls(credential=credential)
        return instance

    @property
    def uuid(self):
        common_name = self.credential.certificate.getSubject().CN
        return UUID(hex=common_name[len(self._UUID_PREFIX):])

    @property
    def cluster_uuid(self):
        return UUID(hex=self.credential.certificate.getSubject().OU)


class ControlCredential(PRecord):
    """
    A certificate and key pair for a control service, signed by a supplied
    certificate authority.

    :ivar FlockerCredential credential: The certificate and key pair
        credential object.
    """
    credential = field(mandatory=True, type=FlockerCredential)

    @classmethod
    def from_path(cls, path, hostname):
        """
        Load a control service certificate and key from the supplied path.

        :param FilePath path: Directory where control service certificate
            and key files are stored.
        :param bytes hostname: The hostname of the control service certificate.
        """
        keypair, certificate = load_certificate_from_path(
            path, b"control-{}.key".format(hostname),
            b"control-{}.crt".format(hostname)
        )
        credential = FlockerCredential(
            path=path, keypair=keypair, certificate=certificate)
        return cls(credential=credential)

    @classmethod
    def initialize(cls, path, authority, hostname, begin=None):
        """
        Generate a certificate signed by the supplied root certificate.

        :param FilePath path: Directory where the certificate will be stored.
        :param RootCredential authority: The certificate authority with
            which this certificate will be signed.
        :param datetime begin: The datetime from which the generated
            certificate should be valid.
        :param bytes hostname: The hostname of the node where the control
            service will be running.
        """
        # The common name for the control service certificate.  This is
        # used to distinguish between control service and node
        # certificates. In practice it gets overridden for validation
        # purposes by the subjectAltName, so we add record there too.
        name = b"control-service"
        # The organizational unit is set to the organizational_unit of the
        # authority, which in our case is the cluster UUID.
        organizational_unit = authority.organizational_unit
        dn = DistinguishedName(
            commonName=name, organizationalUnitName=organizational_unit
        )
        keypair = flocker_keypair()
        request = keypair.keypair.requestObject(dn)
        serial = os.urandom(16).encode(b"hex")
        serial = int(serial, 16)
        try:
            IPAddress(hostname)
        except ValueError:
            alt_name = b"DNS:" + hostname
        else:
            alt_name = b"IP:" + hostname
        cert = sign_certificate_request(
            authority.credential.keypair.keypair,
            authority.credential.certificate.original.get_subject(), request,
            serial, EXPIRY_20_YEARS, 'sha256', start=begin,
            additional_extensions=[
                # subjectAltName overrides common name for validation
                # purposes, and we want to be able to validate against
                # "control-service", so we include it too.
                crypto.X509Extension(b"subjectAltName", False,
                                     b"DNS:control-service," + alt_name),
            ])
        credential = FlockerCredential(
            path=path, keypair=keypair, certificate=cert)
        credential.write_credential_files(
            b"control-{}.key".format(hostname),
            b"control-{}.crt".format(hostname))
        instance = cls(credential=credential)
        return instance

    def _default_options(self, trust_root):
        """
        Construct a ``CertificateOptions`` that exposes this credential's
        certificate and keypair.

        :param trust_root: Trust root to pass to ``CertificateOptions``.

        :return: ``CertificateOptions`` instance with CA validation
            configured.
        """
        key = self.credential.keypair.keypair.original
        certificate = self.credential.certificate.original
        return CertificateOptions(
            privateKey=key, certificate=certificate, trustRoot=trust_root)


class RootCredential(PRecord):
    """
    A credential representing a self-signed certificate authority.
    :ivar FlockerCredential credential: The certificate and key pair
        credential object.
    """
    credential = field(mandatory=True)

    @property
    def common_name(self):
        return self.credential.certificate.getSubject().CN

    @property
    def organizational_unit(self):
        return self.credential.certificate.getSubject().OU

    @classmethod
    def from_path(cls, path):
        try:
            keypair, certificate = load_certificate_from_path(
                path, AUTHORITY_KEY_FILENAME, AUTHORITY_CERTIFICATE_FILENAME
            )
        except PathError as e:
            # Re-raise, but with a more specific message.
            error = b"Unable to load certificate authority file."
            if e.code == 2:
                error = error + (b" Please run `flocker-ca initialize` to "
                                 b"generate a new certificate authority.")
            raise PathError(error, e.filename, e.code, e.failure)
        credential = FlockerCredential(
            path=path, keypair=keypair, certificate=certificate)
        return cls(credential=credential)

    @classmethod
    def initialize(cls, path, name, begin=None, cluster_id=None):
        """
        Generate new private/public key pair and self-sign, then store in given
        directory.

        :param FilePath path: Directory where private key and certificate are
            stored.
        :param bytes name: The name of the cluster. This is used as the
            subject and issuer identities of the generated root certificate.
        :param datetime begin: The datetime from which the generated
            certificate should be valid.
        :param UUID cluster_id: The unique identifier of the cluster for which
            to generate the key and certificate.  If not given, a random
            identifier will be generated.

        :return RootCredential: Initialized certificate authority.
        """
        if cluster_id is None:
            cluster_id = uuid4()

        dn = DistinguishedName(
            commonName=name,
            organizationalUnitName=bytes(cluster_id),
        )
        keypair = flocker_keypair()
        request = keypair.keypair.requestObject(dn)
        serial = os.urandom(16).encode(b"hex")
        serial = int(serial, 16)
        certificate = create_certificate_authority(
            keypair.keypair, dn, request, serial,
            EXPIRY_20_YEARS, b'sha256', start=begin
        )
        credential = FlockerCredential(
            path=path, keypair=keypair, certificate=certificate)
        credential.write_credential_files(
            AUTHORITY_KEY_FILENAME, AUTHORITY_CERTIFICATE_FILENAME)
        instance = cls(credential=credential)
        return instance
