# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Low-level logic for a certificate authority.

Uses ECDSA + SHA256? Or if that turns out to be too difficult RSA 4096-bit
+ SHA 256.
"""

from twisted.internet.ssl import KeyPair


def generate_keypair():
    """
    Create a new key pair.
    """
    #return KeyPair.generate(crypto.TYPE_ECDSA, size=something?)
    pass


class CertificateAuthority(object):
    """
    A certificate authority whose configuration is stored in a specified
    directory.
    """
    def __init__(self, path):
        """
        :param FilePath path: Directory where private key and certificate are
            stored.
        """
        # try to load private key and certificate, raise exception if that
        # fails.

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
        # XXX do we want to do something else/more with the name?
        # More metadata?
        #dn = DistinguishedName(commonName=name)
        #keypair = generate_keypair()
        #request = keypair.requestObject(dn)
        #certificate = keypair.signRequestObject(dn, request, generateaserial, digestAlgorithm='sha256')
        #now write out to some files
        # return cls(path)
