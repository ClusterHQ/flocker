# Copyright (c) Twisted Matrix Laboratories.
"""
Monkey patch twisted.conch.ssh.transport.SSHClientTransport to support
``diffie-hellman-group-exchange-sha256``.

https://clusterhq.atlassian.net/browse/FLOC-2134

This is adapted from the patch at http://twistedmatrix.com/trac/ticket/7672
"""


from twisted.conch.ssh.transport import (
    SSHTransportBase, SSHClientTransport,
    _generateX,
    DH_GENERATOR, DH_PRIME,
    MSG_KEXDH_INIT, MSG_KEX_DH_GEX_REQUEST_OLD,
    DISCONNECT_KEY_EXCHANGE_FAILED,
)
from hashlib import sha1, sha256
from twisted.python import randbytes
from twisted.conch.ssh.common import NS, MP, _MPpow
from twisted.conch import error
from twisted.conch.ssh import keys


def _dh_sha256_patch():
    """
    Monkey patch twisted.conch.ssh.transport.SSHClientTransport to support
    ``diffie-hellman-group-exchange-sha256``.
    """
    supportedKeyExchanges = ['diffie-hellman-group-exchange-sha1',
                             'diffie-hellman-group-exchange-sha256',
                             'diffie-hellman-group1-sha1']

    def _getKey(self, c, sharedSecret, exchangeHash):
        """
        Get one of the keys for authentication/encryption.

        @type c: C{str}
        @type sharedSecret: C{str}
        @type exchangeHash: C{str}
        """
        if self.kexAlg == 'diffie-hellman-group-exchange-sha256':
            h = sha256
        else:
            h = sha1
        k1 = h(sharedSecret + exchangeHash + c + self.sessionID)
        k1 = k1.digest()
        k2 = h(sharedSecret + exchangeHash + k1).digest()
        return k1 + k2

    def ssh_KEXINIT(self, packet):
        """
        Called when we receive a MSG_KEXINIT message.  For a description
        of the packet, see SSHTransportBase.ssh_KEXINIT().  Additionally,
        this method sends the first key exchange packet.  If the agreed-upon
        exchange is diffie-hellman-group1-sha1, generate a public key
        and send it in a MSG_KEXDH_INIT message.  If the exchange is
        diffie-hellman-group-exchange-sha1, ask for a 2048 bit group with a
        MSG_KEX_DH_GEX_REQUEST_OLD message.
        """
        if SSHTransportBase.ssh_KEXINIT(self, packet) is None:
            return  # we disconnected
        if self.kexAlg == 'diffie-hellman-group1-sha1':
            self.x = _generateX(randbytes.secureRandom, 512)
            self.e = _MPpow(DH_GENERATOR, self.x, DH_PRIME)
            self.sendPacket(MSG_KEXDH_INIT, self.e)
        elif self.kexAlg.startswith('diffie-hellman-group-exchange-'):
            self.sendPacket(MSG_KEX_DH_GEX_REQUEST_OLD, '\x00\x00\x08\x00')
        else:
            raise error.ConchError("somehow, the kexAlg has been set "
                                   "to something we don't support")

    def _continueKEXDH_REPLY(self, ignored, pubKey, f, signature):
        """
        The host key has been verified, so we generate the keys.

        @param pubKey: the public key blob for the server's public key.
        @type pubKey: C{str}
        @param f: the server's Diffie-Hellman public key.
        @type f: C{long}
        @param signature: the server's signature, verifying that it has the
            correct private key.
        @type signature: C{str}
        """
        serverKey = keys.Key.fromString(pubKey)
        sharedSecret = _MPpow(f, self.x, DH_PRIME)
        if self.kexAlg == 'diffie-hellman-group-exchange-sha256':
            h = sha256()
        else:
            h = sha1()
        h.update(NS(self.ourVersionString))
        h.update(NS(self.otherVersionString))
        h.update(NS(self.ourKexInitPayload))
        h.update(NS(self.otherKexInitPayload))
        h.update(NS(pubKey))
        h.update(self.e)
        h.update(MP(f))
        h.update(sharedSecret)
        exchangeHash = h.digest()
        if not serverKey.verify(signature, exchangeHash):
            self.sendDisconnect(DISCONNECT_KEY_EXCHANGE_FAILED,
                                'bad signature')
            return
        self._keySetup(sharedSecret, exchangeHash)

    def _continueGEX_REPLY(self, ignored, pubKey, f, signature):
        """
        The host key has been verified, so we generate the keys.

        @param pubKey: the public key blob for the server's public key.
        @type pubKey: C{str}
        @param f: the server's Diffie-Hellman public key.
        @type f: C{long}
        @param signature: the server's signature, verifying that it has the
            correct private key.
        @type signature: C{str}
        """
        serverKey = keys.Key.fromString(pubKey)
        sharedSecret = _MPpow(f, self.x, self.p)
        if self.kexAlg == 'diffie-hellman-group-exchange-sha256':
            h = sha256()
        else:
            h = sha1()
        h.update(NS(self.ourVersionString))
        h.update(NS(self.otherVersionString))
        h.update(NS(self.ourKexInitPayload))
        h.update(NS(self.otherKexInitPayload))
        h.update(NS(pubKey))
        h.update('\x00\x00\x08\x00')
        h.update(MP(self.p))
        h.update(MP(self.g))
        h.update(self.e)
        h.update(MP(f))
        h.update(sharedSecret)
        exchangeHash = h.digest()
        if not serverKey.verify(signature, exchangeHash):
            self.sendDisconnect(DISCONNECT_KEY_EXCHANGE_FAILED,
                                'bad signature')
            return
        self._keySetup(sharedSecret, exchangeHash)

    for var, val in locals().items():
        setattr(SSHClientTransport, var, val)


def _patch_7672_needed():
    """
    Check if patching ``SSHClientTransport`` sf necessary.
    This will be true if ``diffie-hellman-group-exchange-sha256``
    is not a supported keyexchange.
    """
    return ('diffie-hellman-group-exchange-sha256'
            not in SSHClientTransport.supportedKeyExchanges)

patch_7672_applied = False


def patch_twisted_7672():
    """
    Apply monkeypatches.
    """
    global patch_7672_applied
    if patch_7672_applied:
        return
    if _patch_7672_needed():
        patch_7672_applied = True
        _dh_sha256_patch()
