# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Utilities to help with unit and functional testing of ssh."""

import os
from operator import setitem, delitem
from signal import SIGKILL
from unittest import skipIf

from subprocess import check_call, check_output

from zope.interface import implementer

from ipaddr import IPAddress

from twisted.python.components import registerAdapter
from twisted.internet import reactor
from twisted.cred.portal import IRealm, Portal

try:
    from twisted.conch.ssh.keys import Key
    from twisted.conch.checkers import SSHPublicKeyDatabase
    from twisted.conch.interfaces import ISession
    from twisted.conch.openssh_compat.factory import OpenSSHFactory
    from twisted.conch.unix import (
        SSHSessionForUnixConchUser,
        UnixConchUser,
    )
    _have_conch = True
except ImportError:
    SSHPublicKeyDatabase = UnixConchUser = object
    _have_conch = False

if_conch = skipIf(not _have_conch, "twisted.conch must be useable.")


class _InMemoryPublicKeyChecker(SSHPublicKeyDatabase):
    """
    Check SSH public keys in-memory.
    """

    def __init__(self, public_key):
        """
        :param Key public_key: The public key we will accept.
        """
        self._key = public_key

    def checkKey(self, credentials):
        """
        Validate some SSH key credentials.

        Access is granted only to root since that is the user we expect
        for connections from ZFS agents.
        """
        return (self._key.blob() == credentials.blob and
                credentials.username == b"root")


class _FixedHomeConchUser(UnixConchUser):
    """
    An SSH user with a fixed, configurable home directory.

    This is like a normal UNIX SSH user except the user's home directory is not
    determined by the ``pwd`` database.
    """
    def __init__(self, username, home):
        """
        :param FilePath home: The path of the directory to use as this user's
            home directory.
        """
        UnixConchUser.__init__(self, username)
        self._home = home

    def getHomeDir(self):
        """
        Give back the pre-determined home directory.
        """
        return self._home.path

    def getUserGroupId(self):
        """
        Give back some not-strictly-legal ``None`` UID/GID
        identifiers.  This prevents the Conch server from trying to
        switch IDs (which it can't do if it is not running as root).
        """
        return None, None


@implementer(ISession)
class _EnvironmentSSHSessionForUnixConchUser(SSHSessionForUnixConchUser):
    """
    SSH Session that correctly sets HOME.

    Work-around for https://twistedmatrix.com/trac/ticket/7936.
    """

    def execCommand(self, proto, cmd):
        self.environ['HOME'] = self.avatar.getHomeDir()
        return SSHSessionForUnixConchUser.execCommand(self, proto, cmd)


registerAdapter(
    _EnvironmentSSHSessionForUnixConchUser, _FixedHomeConchUser, ISession)


@implementer(IRealm)
class _UnixSSHRealm(object):
    """
    An ``IRealm`` for a Conch server which gives out ``_FixedHomeConchUser``
    users.
    """
    def __init__(self, home):
        self.home = home

    def requestAvatar(self, username, mind, *interfaces):
        user = _FixedHomeConchUser(username, self.home)
        return interfaces[0], user, user.logout


class _ConchServer(object):
    """
    A helper for a test fixture to run an SSH server using Twisted Conch.

    :ivar IPv4Address ip: The address the server is listening on.
    :ivar int port: The port number the server is listening on.
    :ivar _port: An object which provides ``IListeningPort`` and represents the
        listening Conch server.

    :ivar FilePath home_path: The path of the home directory of the user which
        is allowed to authenticate against this server.

    :ivar FilePath key_path: The path of an SSH private key which can be used
        to authenticate against the server.

    :ivar FilePath host_key_path: The path of the server's private host key.
    """
    def __init__(self, base_path):
        """
        :param FilePath base_path: The path beneath which all of the temporary
            SSH server-related files will be created.  An ``ssh`` directory
            will be created as a child of this directory to hold the key pair
            that is generated.  An ``sshd`` directory will also be created here
            to hold the generated host key.  A ``home`` directory is also
            created here and used as the home directory for shell logins to the
            server.
        """
        self.home = base_path.child(b"home")
        self.home.makedirs()

        ssh_path = base_path.child(b"ssh")
        ssh_path.makedirs()
        self.key_path = ssh_path.child(b"key")
        check_call(
            [b"ssh-keygen",
             # Specify the path where the generated key is written.
             b"-f", self.key_path.path,
             # Specify an empty passphrase.
             b"-N", b"",
             # Generate as little output as possible.
             b"-q"])
        key = Key.fromFile(self.key_path.path)

        sshd_path = base_path.child(b"sshd")
        sshd_path.makedirs()
        self.host_key_path = sshd_path.child(b"ssh_host_key")
        check_call(
            [b"ssh-keygen",
             # See above for option explanations.
             b"-f", self.host_key_path.path,
             b"-N", b"",
             b"-q"])

        factory = OpenSSHFactory()
        realm = _UnixSSHRealm(self.home)
        checker = _InMemoryPublicKeyChecker(public_key=key.public())
        factory.portal = Portal(realm, [checker])
        factory.dataRoot = sshd_path.path
        factory.moduliRoot = b"/etc/ssh"

        self._port = reactor.listenTCP(0, factory, interface=b"127.0.0.1")
        self.ip = IPAddress(self._port.getHost().host)
        self.port = self._port.getHost().port

    def restore(self):
        """
        Shut down the SSH server.

        :return: A ``Deferred`` that fires when this has been done.
        """
        return self._port.stopListening()


@if_conch
def create_ssh_server(base_path):
    """
    :py:func:`create_ssh_server` is a fixture which creates and runs a new SSH
    server and stops it later.  Use the :py:meth:`restore` method of the
    returned object to stop the server.

    :param FilePath base_path: The path to a directory in which key material
        will be generated.
    """
    return _ConchServer(base_path)


class _SSHAgent(object):
    """
    A helper for a test fixture to run an `ssh-agent` process.

    :ivar FilePath key_path: The path of an SSH private key which can be used
        to authenticate against the server.
    """
    def __init__(self, key_file):
        """
        Start an `ssh-agent` and add its socket path and pid to the global
        environment so that SSH sub-processes can use it for authentication.

        :param FilePath key_file: An SSH private key file which can be used
            when authenticating with SSH servers.
        """
        self._cleanups = []

        output = check_output([b"ssh-agent", b"-c"]).splitlines()
        # setenv SSH_AUTH_SOCK /tmp/ssh-5EfGti8RPQbQ/agent.6390;
        # setenv SSH_AGENT_PID 6391;
        # echo Agent pid 6391;
        sock = output[0].split()[2][:-1]
        pid = output[1].split()[2][:-1]
        self._pid = int(pid)

        def patchdict(k, v):
            if k in os.environ:
                self._cleanups.append(
                    lambda old=os.environ[k]: setitem(os.environ, k, old))
            else:
                self._cleanups.append(lambda: delitem(os.environ, k))

            os.environ[k] = v

        patchdict(b"SSH_AUTH_SOCK", sock)
        patchdict(b"SSH_AGENT_PID", pid)

        with open(os.devnull, "w") as discard:
            # See https://clusterhq.atlassian.net/browse/FLOC-192
            check_call(
                [b"ssh-add", key_file.path],
                stdout=discard, stderr=discard)

    def restore(self):
        """
        Shut down the SSH agent and restore the test environment to its
        previous state.
        """
        for cleanup in self._cleanups:
            cleanup()
        os.kill(self._pid, SIGKILL)


def create_ssh_agent(key_file, testcase=None):
    """
    :py:func:`create_ssh_agent` is a fixture which creates and runs a new SSH
    agent and stops it later.  Use the :py:meth:`restore` method of the
    returned object to stop the server.

    :param FilePath key_file: The path of an SSH private key which can be
        used when authenticating with SSH servers.
    :param TestCase testcase: The ``TestCase`` object requiring the SSH
        agent. Optional, adds a cleanup if supplied.

    :rtype: _SSHAgent
    """
    agent = _SSHAgent(key_file)
    if testcase:
        testcase.addCleanup(agent.restore)
    return agent
