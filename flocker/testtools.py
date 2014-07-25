# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Various utilities to help with unit and functional testing."""

from __future__ import absolute_import

import gc
import io
import socket
import sys
import os
import pwd
import grp
from operator import setitem, delitem
from collections import namedtuple
from contextlib import contextmanager
from random import random
import shutil
from signal import SIGKILL
from subprocess import check_call, check_output
from functools import wraps

from zope.interface import implementer
from zope.interface.verify import verifyClass, verifyObject

from ipaddr import IPAddress

from twisted.internet.interfaces import IProcessTransport, IReactorProcess
from twisted.python.filepath import FilePath, Permissions
from twisted.internet.task import Clock, deferLater
from twisted.internet.defer import maybeDeferred, Deferred
from twisted.internet.error import ConnectionDone
from twisted.internet import reactor
from twisted.cred.portal import IRealm, Portal
from twisted.conch.ssh.keys import Key
from twisted.conch.checkers import SSHPublicKeyDatabase
from twisted.conch.openssh_compat.factory import OpenSSHFactory
from twisted.conch.unix import UnixConchUser
from twisted.trial.unittest import SynchronousTestCase, SkipTest
from twisted.internet.protocol import Factory, Protocol

from characteristic import attributes

from . import __version__
from .common.script import (
    FlockerScriptRunner, ICommandLineScript)
from .volume.service import VolumeService
from .volume.filesystems.memory import FilesystemStoragePool


def create_volume_service(test):
    """
    Create a new ``VolumeService``.

    :param TestCase test: A unit test which will shut down the service
        when done.

    :return: The ``VolumeService`` created.
    """
    service = VolumeService(FilePath(test.mktemp()),
                            FilesystemStoragePool(FilePath(test.mktemp())),
                            reactor=Clock())
    service.startService()
    test.addCleanup(service.stopService)
    return service


@implementer(IProcessTransport)
class FakeProcessTransport(object):
    """
    Mock process transport to observe signals sent to a process.

    @ivar signals: L{list} of signals sent to process.
    """

    def __init__(self):
        self.signals = []

    def signalProcess(self, signal):
        self.signals.append(signal)


class SpawnProcessArguments(namedtuple(
                            'ProcessData',
                            'processProtocol executable args env path '
                            'uid gid usePTY childFDs transport')):
    """
    Object recording the arguments passed to L{FakeProcessReactor.spawnProcess}
    as well as the L{IProcessTransport} that was connected to the protocol.

    @ivar transport: Fake transport connected to the protocol.
    @type transport: L{IProcessTransport}

    @see L{twisted.internet.interfaces.IReactorProcess.spawnProcess}
    """


@implementer(IReactorProcess)
class FakeProcessReactor(Clock):
    """
    Fake reactor implmenting process support.

    @ivar processes: List of process that have been spawned
    @type processes: L{list} of L{SpawnProcessArguments}.
    """

    def __init__(self):
        Clock.__init__(self)
        self.processes = []

    def timeout(self):
        if self.calls:
            return max(0, self.calls[0].getTime() - self.seconds())
        return 0

    def spawnProcess(self, processProtocol, executable, args=(), env={},
                     path=None, uid=None, gid=None, usePTY=0, childFDs=None):
        transport = FakeProcessTransport()
        self.processes.append(SpawnProcessArguments(
            processProtocol, executable, args, env, path, uid, gid, usePTY,
            childFDs, transport=transport))
        processProtocol.makeConnection(transport)
        return transport


verifyClass(IReactorProcess, FakeProcessReactor)


@contextmanager
def assertNoFDsLeaked(test_case):
    """Context manager that asserts no file descriptors are leaked.

    :param test_case: The ``TestCase`` running this unit test.
    """
    # Make sure there's no file descriptors that will be cleared by GC
    # later on:
    gc.collect()

    def process_fds():
        path = FilePath(b"/proc/self/fd")
        return set([child.basename() for child in path.children()])

    fds = process_fds()
    try:
        yield
    finally:
        test_case.assertEqual(process_fds(), fds)


def loop_until(predicate):
    """Call predicate every 0.1 seconds, until it returns something ``Truthy``.

    :param predicate: Callable returning termination condition.
    :type predicate: 0-argument callable returning a Deferred.

    :return: A ``Deferred`` firing with the first ``Truthy`` response from
        ``predicate``.
    """
    d = maybeDeferred(predicate)

    def loop(result):
        if not result:
            d = deferLater(reactor, 0.1, predicate)
            d.addCallback(loop)
            return d
        return result
    d.addCallback(loop)
    return d


def random_name():
    """Return a short, random name.

    :return name: A random ``unicode`` name.
    """
    return u"%d" % (int(random() * 1e12),)


def help_problems(command_name, help_text):
    """Identify and return a list of help text problems.

    :param unicode command_name: The name of the command which should appear in
        the help text.
    :param bytes help_text: The full help text to be inspected.
    :return: A list of problems found with the supplied ``help_text``.
    :rtype: list
    """
    problems = []
    expected_start = u'Usage: {command}'.format(
        command=command_name).encode('utf8')
    if not help_text.startswith(expected_start):
        problems.append(
            'Does not begin with {expected}. Found {actual} instead'.format(
                expected=repr(expected_start),
                actual=repr(help_text[:len(expected_start)])
            )
        )
    return problems


class FakeSysModule(object):
    """A ``sys`` like substitute.

    For use in testing the handling of `argv`, `stdout` and `stderr` by command
    line scripts.

    :ivar list argv: See ``__init__``
    :ivar stdout: A :py:class:`io.BytesIO` object representing standard output.
    :ivar stderr: A :py:class:`io.BytesIO` object representing standard error.
    """
    def __init__(self, argv=None):
        """Initialise the fake sys module.

        :param list argv: The arguments list which should be exposed as
            ``sys.argv``.
        """
        if argv is None:
            argv = []
        self.argv = argv
        # io.BytesIO is not quite the same as sys.stdout/stderr
        # particularly with respect to unicode handling.  So,
        # hopefully the implementation doesn't try to write any
        # unicode.
        self.stdout = io.BytesIO()
        self.stderr = io.BytesIO()


class FlockerScriptTestsMixin(object):
    """Common tests for scripts that can be run via L{FlockerScriptRunner}

    :ivar ICommandLineScript script: The script class under test.
    :ivar usage.Options options: The options parser class to use in the test.
    :ivar text command_name: The name of the command represented by ``script``.
    """

    script = None
    options = None
    command_name = None

    def test_interface(self):
        """
        A script that is meant to be run by ``FlockerScriptRunner`` must
        implement ``ICommandLineScript``.
        """
        self.assertTrue(verifyObject(ICommandLineScript, self.script()))

    def test_incorrect_arguments(self):
        """
        ``FlockerScriptRunner.main`` exits with status 1 and prints help to
        `stderr` if supplied with unexpected arguments.
        """
        sys = FakeSysModule(argv=[self.command_name, b'--unexpected_argument'])
        script = FlockerScriptRunner(
            reactor=None, script=self.script(), options=self.options(),
            sys_module=sys)
        error = self.assertRaises(SystemExit, script.main)
        error_text = sys.stderr.getvalue()
        self.assertEqual(
            (1, []),
            (error.code, help_problems(self.command_name, error_text))
        )


class StandardOptionsTestsMixin(object):
    """Tests for classes decorated with ``flocker_standard_options``.

    Tests for the standard options that should be available on every flocker
    command.

    :ivar usage.Options options: The ``usage.Options`` class under test.
    """
    options = None

    def test_sys_module_default(self):
        """
        ``flocker_standard_options`` adds a ``_sys_module`` attribute which is
        ``sys`` by default.
        """
        self.assertIs(sys, self.options()._sys_module)

    def test_sys_module_override(self):
        """
        ``flocker_standard_options`` adds a ``sys_module`` argument to the
        initialiser which is assigned to ``_sys_module``.
        """
        dummy_sys_module = object()
        self.assertIs(
            dummy_sys_module,
            self.options(sys_module=dummy_sys_module)._sys_module
        )

    def test_version(self):
        """
        Flocker commands have a `--version` option which prints the current
        version string to stdout and causes the command to exit with status
        `0`.
        """
        sys = FakeSysModule()
        error = self.assertRaises(
            SystemExit,
            self.options(sys_module=sys).parseOptions,
            ['--version']
        )
        self.assertEqual(
            (__version__ + '\n', 0),
            (sys.stdout.getvalue(), error.code)
        )

    def test_verbosity_default(self):
        """
        Flocker commands have `verbosity` of `0` by default.
        """
        options = self.options()
        self.assertEqual(0, options['verbosity'])

    def test_verbosity_option(self):
        """
        Flocker commands have a `--verbose` option which increments the
        configured verbosity by `1`.
        """
        options = self.options()
        # The command may otherwise give a UsageError
        # "Wrong number of arguments." if there are arguments required.
        # See https://github.com/ClusterHQ/flocker/issues/184 about a solution
        # which does not involve patching.
        self.patch(options, "parseArgs", lambda: None)
        options.parseOptions(['--verbose'])
        self.assertEqual(1, options['verbosity'])

    def test_verbosity_option_short(self):
        """
        Flocker commands have a `-v` option which increments the configured
        verbosity by 1.
        """
        options = self.options()
        # The command may otherwise give a UsageError
        # "Wrong number of arguments." if there are arguments required.
        # See https://github.com/ClusterHQ/flocker/issues/184 about a solution
        # which does not involve patching.
        self.patch(options, "parseArgs", lambda: None)
        options.parseOptions(['-v'])
        self.assertEqual(1, options['verbosity'])

    def test_verbosity_multiple(self):
        """
        `--verbose` can be supplied multiple times to increase the verbosity.
        """
        options = self.options()
        # The command may otherwise give a UsageError
        # "Wrong number of arguments." if there are arguments required.
        # See https://github.com/ClusterHQ/flocker/issues/184 about a solution
        # which does not involve patching.
        self.patch(options, "parseArgs", lambda: None)
        options.parseOptions(['-v', '--verbose'])
        self.assertEqual(2, options['verbosity'])


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
        for connections from ``flocker-cli`` and ``flocker-changestate``.
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


@implementer(IRealm)
class UnixSSHRealm(object):
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
        realm = UnixSSHRealm(self.home)
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
            # See https://github.com/clusterhq/flocker/issues/192
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


def make_with_init_tests(record_type, kwargs, expected_defaults=None):
    """
    Return a ``TestCase`` which tests that ``record_type.__init__`` accepts the
    supplied ``kwargs`` and exposes them as public attributes.

    :param record_type: The class with an ``__init__`` method to be tested.
    :param kwargs: The keyword arguments which will be supplied to the
        ``__init__`` method.
    :param dict expected_defaults: The default keys and default values of
        arguments which have defaults and which may be omitted when calling the
        initialiser.
    :returns: A ``TestCase``.
    """
    if expected_defaults is None:
        expected_defaults = {}

    unknown_defaults = set(expected_defaults.keys()) - set(kwargs.keys())
    if unknown_defaults:
        raise TypeError(
            'expected_defaults contained the following unrecognized keys: '
            '{}'.format(tuple(unknown_defaults)))

    required_kwargs = kwargs.copy()
    for k, v in expected_defaults.items():
        required_kwargs.pop(k)

    class WithInitTests(SynchronousTestCase):
        """
        Tests for classes decorated with ``with_init``.
        """
        def test_init(self):
            """
            The record type accepts keyword arguments which are exposed as
            public attributes.
            """
            record = record_type(**kwargs)
            self.assertEqual(
                kwargs.values(),
                [getattr(record, key) for key in kwargs.keys()]
            )

        def test_optional_arguments(self):
            """
            The record type initialiser has arguments which may be omitted.
            """
            try:
                record = record_type(**required_kwargs)
            except ValueError as e:
                self.fail(
                    'One of the following arguments was expected to be '
                    'optional but appears to be required: %r. '
                    'Error was: %r' % (
                        expected_defaults.keys(), e))

            self.assertEqual(
                required_kwargs.values(),
                [getattr(record, key) for key in required_kwargs.keys()]
            )

        def test_optional_defaults(self):
            """
            The optional arguments have the expected defaults.
            """
            try:
                record = record_type(**required_kwargs)
            except ValueError as e:
                self.fail(
                    'One of the following arguments was expected to be '
                    'optional but appears to be required: %r. '
                    'Error was: %r' % (
                        expected_defaults.keys(), e))
            self.assertEqual(
                expected_defaults.values(),
                [getattr(record, key) for key in expected_defaults.keys()]
            )

    return WithInitTests


def find_free_port(interface='127.0.0.1', socket_family=socket.AF_INET,
                   socket_type=socket.SOCK_STREAM):
    """
    Ask the platform to allocate a free port on the specified interface, then
    release the socket and return the address which was allocated.

    Copied from ``twisted.internet.test.connectionmixins.findFreePort``.

    :param bytes interface: The local address to try to bind the port on.
    :param int socket_family: The socket family of port.
    :param int socket_type: The socket type of the port.

    :return: A two-tuple of address and port, like that returned by
        ``socket.getsockname``.
    """
    address = socket.getaddrinfo(interface, 0)[0][4]
    probe = socket.socket(socket_family, socket_type)
    try:
        probe.bind(address)
        return probe.getsockname()
    finally:
        probe.close()


def make_capture_protocol():
    """
    Return a ``Deferred``, and a ``Protocol`` which will capture bytes and fire
    the ``Deferred`` when its connection is lost.

    :returns: A 2-tuple of ``Deferred`` and ``Protocol`` instance.
    :rtype: tuple
    """
    d = Deferred()
    captured_data = []

    class Recorder(Protocol):
        def dataReceived(self, data):
            captured_data.append(data)

        def connectionLost(self, reason):
            if reason.check(ConnectionDone):
                d.callback(b''.join(captured_data))
            else:
                d.errback(reason)
    return d, Recorder()


class ProtocolPoppingFactory(Factory):
    """
    A factory which only creates a fixed list of protocols.

    For example if in a test you want to ensure that a test server only handles
    a single connection, you'd supply a list of one ``Protocol``
    instance. Subsequent requests will result in an ``IndexError``.
    """
    def __init__(self, protocols):
        """
        :param list protocols: A list of ``Protocol`` instances which will be
            used for successive connections.
        """
        self.protocols = protocols

    def buildProtocol(self, addr):
        return self.protocols.pop()


@attributes(['source_dir', 'tag', 'working_dir'])
class DockerImageBuilder(object):
    """
    Build a docker image, tag it, and optionally remove the image later.

    :ivar bytes docker_dir: The path to the directory containing a
        `Dockerfile`.
    :ivar bytes tag: The tag name to be applied to the built image.
    """
    def _process_template(self, template_file, target_file, replacements):
        """
        Fill in the placeholders in `template_file` with the `replacements` and
        write the result to `target_file`.

        :param FilePath template_file: The file containing the placeholders.
        :param FilePath target_file: The file to which the result will be
            written.
        :param dict replacements: A dictionary of variable names and
            replacement values.
        """
        with template_file.open() as f:
            template = f.read().decode('utf8')
        target_file.setContent(template.format(**replacements))

    def build(self, dockerfile_variables=None):
        """
        Build an image and tag it in the local Docker repository.

        :param dict dockerfile_variables: A dictionary of replacements which
            will be applied to a `Dockerfile.in` template file if such a file
            exists.
        """
        if dockerfile_variables is None:
            dockerfile_variables = {}

        if not self.working_dir.exists():
            self.working_dir.makedirs()

        docker_dir = self.working_dir.child('docker')
        shutil.copytree(self.source_dir.path, docker_dir.path)
        template_file = docker_dir.child('Dockerfile.in')
        docker_file = docker_dir.child('Dockerfile')
        if template_file.exists() and not docker_file.exists():
            self._process_template(
                template_file, docker_file, dockerfile_variables)
        # XXX: This dumps lots of debug output to stderr which messes up the
        # test results output. It's useful debug info incase of a test failure
        # so it would be better to send it to the test.log file. See
        # https://github.com/ClusterHQ/flocker/issues/171
        command = [
            b'docker', b'build',
            # Always clean up intermediate containers in case of failures.
            b'--force-rm',
            b'--tag=%s' % (self.tag,),
            docker_dir.path
        ]
        check_call(command)


def skip_on_broken_permissions(test_method):
    """
    Skips the wrapped test when the temporary directory is on a
    filesystem with broken permissions.

    Virtualbox's shared folder (as used for :file:`/vagrant`) doesn't entirely
    respect changing permissions. For example, this test detects running on a
    shared folder by the fact that all permissions can't be removed from a
    file.

    :param callable test_method: Test method to wrap.
    :return: The wrapped method.
    :raise SkipTest: when the temporary directory is on a filesystem with
        broken permissions.
    """
    @wraps(test_method)
    def wrapper(case, *args, **kwargs):
        test_file = FilePath(case.mktemp())
        test_file.touch()
        test_file.chmod(0o000)
        permissions = test_file.getPermissions()
        test_file.chmod(0o777)
        if permissions != Permissions(0o000):
            raise SkipTest(
                "Can't run test on filesystem with broken permissions.")
        return test_method(case, *args, **kwargs)
    return wrapper


class run_as_user(object):
    def __init__(self, user='nobody'):
        self.uid_name = user

    def __call__(self, test_method):
        @wraps(test_method)
        def wrapper(case, *args, **kwargs):
            if os.getuid() != 0:
                return test_method(case, *args, **kwargs)
            running_uid = pwd.getpwnam(self.uid_name).pw_uid
            result = case.mktemp()
            path = FilePath(result)
            for p in path.parents():
                if '_trial_temp' in p.path:
                    p.chmod(0o777)
            if os.getuid() == 0:
                os.seteuid(running_uid)
                case.addCleanup(os.seteuid, 0)
            return test_method(case, *args, **kwargs)
        return wrapper
