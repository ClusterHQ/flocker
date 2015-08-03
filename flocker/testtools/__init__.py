# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Various utilities to help with unit and functional testing.
"""

from __future__ import absolute_import

import gc
import io
import socket
import sys
import os
import pwd
from collections import namedtuple
from contextlib import contextmanager
from random import randrange
import shutil
from functools import wraps, partial
from unittest import skipIf, skipUnless
from inspect import getfile, getsourcelines
from StringIO import StringIO
from subprocess import PIPE, STDOUT, CalledProcessError, Popen

from bitmath import GiB, MiB

from pyrsistent import PRecord, field

from docker import Client as DockerClient
from eliot import ActionType, Message, MessageType, start_action, fields, Field
from eliot.twisted import DeferredContext

from zope.interface import implementer
from zope.interface.verify import verifyClass, verifyObject

from twisted.internet.interfaces import (
    IProcessTransport, IReactorProcess, IReactorCore,
)
from twisted.python.filepath import FilePath, Permissions
from twisted.python.reflect import prefixedMethodNames, safe_repr
from twisted.internet.task import Clock, deferLater
from twisted.internet.defer import maybeDeferred, Deferred, succeed
from twisted.internet.error import ConnectionDone
from twisted.internet import reactor
from twisted.trial.unittest import SynchronousTestCase, SkipTest
from twisted.internet.protocol import Factory, ProcessProtocol, Protocol
from twisted.test.proto_helpers import MemoryReactor
from twisted.python.procutils import which
from twisted.trial.unittest import TestCase
from twisted.protocols.amp import AMP, InvalidSignature
from twisted.python.logfile import LogFile

from .. import __version__
from ..common.script import (
    FlockerScriptRunner, ICommandLineScript)


# This is currently set to the minimum size for a SATA based Rackspace Cloud
# Block Storage volume. See:
# * http://www.rackspace.com/knowledge_center/product-faq/cloud-block-storage
REALISTIC_BLOCKDEVICE_SIZE = int(GiB(100).to_Byte().value)


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
    :raise SkipTest: when /proc virtual filesystem is not available.
    """
    # Make sure there's no file descriptors that will be cleared by GC
    # later on:
    gc.collect()

    def process_fds():
        path = FilePath(b"/proc/self/fd")
        if not path.exists():
            raise SkipTest("/proc is not available.")

        return set([child.basename() for child in path.children()])

    fds = process_fds()
    try:
        yield
    finally:
        test_case.assertEqual(process_fds(), fds)


def assert_equal_comparison(case, a, b):
    """
    Assert that ``a`` equals ``b``.

    :param a: Any object to compare to ``b``.
    :param b: Any object to compare to ``a``.

    :raise: If ``a == b`` evaluates to ``False`` or if ``a != b`` evaluates to
        ``True``, ``case.failureException`` is raised.
    """
    equal = a == b
    unequal = a != b

    messages = []
    if not equal:
        messages.append("a == b evaluated to False")
    if unequal:
        messages.append("a != b evaluated to True")

    if messages:
        case.fail(
            "Expected a and b to be equal: " + "; ".join(messages))


def assert_not_equal_comparison(case, a, b):
    """
    Assert that ``a`` does not equal ``b``.

    :param a: Any object to compare to ``b``.
    :param b: Any object to compare to ``a``.

    :raise: If ``a == b`` evaluates to ``True`` or if ``a != b`` evaluates to
        ``False``, ``case.failureException`` is raised.
    """
    equal = a == b
    unequal = a != b

    messages = []
    if equal:
        messages.append("a == b evaluated to True")
    if not unequal:
        messages.append("a != b evaluated to False")

    if messages:
        case.fail(
            "Expected a and b to be not-equal: " + "; ".join(messages))


def function_serializer(function):
    """
    Serialize the given function for logging by eliot.

    :param function: Function to serialize.

    :return: Serialized version of function for inclusion in logs.
    """
    try:
        return {
            "function": str(function),
            "file": getfile(function),
            "line": getsourcelines(function)[1]
        }
    except IOError:
        # One debugging method involves changing .py files and is incompatible
        # with inspecting the source.
        return {
            "function": str(function),
        }

LOOP_UNTIL_ACTION = ActionType(
    action_type="flocker:testtools:loop_until",
    startFields=[Field("predicate", function_serializer)],
    successFields=[Field("result", serializer=safe_repr)],
    description="Looping until predicate is true.")

LOOP_UNTIL_ITERATION_MESSAGE = MessageType(
    message_type="flocker:testtools:loop_until:iteration",
    fields=[Field("result", serializer=safe_repr)],
    description="Predicate failed, trying again.")


def loop_until(predicate, reactor=reactor):
    """Call predicate every 0.1 seconds, until it returns something ``Truthy``.

    :param predicate: Callable returning termination condition.
    :type predicate: 0-argument callable returning a Deferred.

    :param reactor: The reactor implementation to use to delay.
    :type reactor: ``IReactorTime``.

    :return: A ``Deferred`` firing with the first ``Truthy`` response from
        ``predicate``.
    """
    action = LOOP_UNTIL_ACTION(predicate=predicate)

    d = action.run(DeferredContext, maybeDeferred(action.run, predicate))

    def loop(result):
        if not result:
            LOOP_UNTIL_ITERATION_MESSAGE(
                result=result
            ).write()
            d = deferLater(reactor, 0.1, action.run, predicate)
            d.addCallback(partial(action.run, loop))
            return d
        action.addSuccessFields(result=result)
        return result
    d.addCallback(loop)
    return d.addActionFinish()


def random_name(case):
    """
    Return a short, random name.

    :param TestCase case: The test case being run.  The test method that is
        running will be mixed into the name.

    :return name: A random ``unicode`` name.
    """
    return u"{}-{}".format(case.id().replace(u".", u"_"), randrange(10 ** 6))


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
        sys_module = FakeSysModule(
            argv=[self.command_name, b'--unexpected_argument'])
        script = FlockerScriptRunner(
            reactor=None, script=self.script(), options=self.options(),
            sys_module=sys_module)
        error = self.assertRaises(SystemExit, script.main)
        error_text = sys_module.stderr.getvalue()
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
        fake_sys_module = FakeSysModule()
        self.assertIs(
            fake_sys_module,
            self.options(sys_module=fake_sys_module)._sys_module
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
        # See https://clusterhq.atlassian.net/browse/FLOC-184 about a solution
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
        # See https://clusterhq.atlassian.net/browse/FLOC-184 about a solution
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
        # See https://clusterhq.atlassian.net/browse/FLOC-184 about a solution
        # which does not involve patching.
        self.patch(options, "parseArgs", lambda: None)
        options.parseOptions(['-v', '--verbose'])
        self.assertEqual(2, options['verbosity'])

    def test_logfile_default(self):
        """
        `--logfile` is optional and if ommited, the default value will be
        ``stdout``.
        """
        sys = FakeSysModule()
        options = self.options(sys_module=sys)
        # The command may otherwise give a UsageError
        # "Wrong number of arguments." if there are arguments required.
        # See https://clusterhq.atlassian.net/browse/FLOC-184 about a solution
        # which does not involve patching.
        self.patch(options, "parseArgs", lambda: None)
        options.parseOptions([])
        self.assertIs(sys.stdout, options['logfile'])

    def test_logfile_override(self):
        """
        If `--logfile` is supplied, its value is stored as a
        ``twisted.python.logfile.LogFile``.
        """
        options = self.options()
        # The command may otherwise give a UsageError
        # "Wrong number of arguments." if there are arguments required.
        # See https://clusterhq.atlassian.net/browse/FLOC-184 about a solution
        # which does not involve patching.
        self.patch(options, "parseArgs", lambda: None)
        expected_path = FilePath(self.mktemp()).path
        options.parseOptions(['--logfile={}'.format(expected_path)])
        logfile = options['logfile']
        self.assertEqual(
            (LogFile, expected_path, int(MiB(100).to_Byte().value), 5),
            (logfile.__class__, logfile.path,
             logfile.rotateLength, logfile.maxRotatedFiles)
        )


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


class DockerImageBuilder(PRecord):
    """
    Build a docker image, tag it, and remove the image later.

    :ivar TestCase test: The test the builder is being used in.
    :ivar FilePath source_dir: The path to the directory containing a
        ``Dockerfile.in`` file.
    :ivar bool cleanup: If ``True`` then cleanup after the test is done.
    """
    test = field(mandatory=True)
    source_dir = field(mandatory=True)
    cleanup = field(mandatory=True, initial=True)

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

        :return: ``Deferred bytes`` with the tag name applied to the built
            image.
        """
        if dockerfile_variables is None:
            dockerfile_variables = {}

        working_dir = FilePath(self.test.mktemp())
        working_dir.makedirs()

        docker_dir = working_dir.child('docker')
        shutil.copytree(self.source_dir.path, docker_dir.path)
        template_file = docker_dir.child('Dockerfile.in')
        docker_file = docker_dir.child('Dockerfile')
        if template_file.exists() and not docker_file.exists():
            self._process_template(
                template_file, docker_file, dockerfile_variables)
        tag = b"flockerlocaltests/" + random_name(self.test).lower()

        # XXX: This dumps lots of debug output to stderr which messes up the
        # test results output. It's useful debug info incase of a test failure
        # so it would be better to send it to the test.log file. See
        # https://clusterhq.atlassian.net/browse/FLOC-171
        command = [
            b'docker', b'build',
            # Always clean up intermediate containers in case of failures.
            b'--force-rm',
            b'--tag=%s' % (tag,),
            docker_dir.path
        ]
        d = logged_run_process(reactor, command)
        if self.cleanup:
            def remove_image():
                client = DockerClient(version="1.15")
                for container in client.containers():
                    if container[u"Image"] == tag + ":latest":
                        client.remove_container(container[u"Names"][0])
                client.remove_image(tag, force=True)
            self.test.addCleanup(remove_image)
        return d.addCallback(lambda ignored: tag)


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


@contextmanager
def attempt_effective_uid(username, suppress_errors=False):
    """
    A context manager to temporarily change the effective user id.

    :param bytes username: The username whose uid will take effect.
    :param bool suppress_errors: Set to `True` to suppress `OSError`
        ("Operation not permitted") when running as a non-root user.
    """
    original_euid = os.geteuid()
    new_euid = pwd.getpwnam(username).pw_uid
    restore_euid = False

    if original_euid != new_euid:
        try:
            os.seteuid(new_euid)
        except OSError as e:
            # Only handle "Operation not permitted" errors.
            if not suppress_errors or e.errno != 1:
                raise
        else:
            restore_euid = True
    try:
        yield
    finally:
        if restore_euid:
            os.seteuid(original_euid)


def assertContainsAll(haystack, needles, test_case):
    """
    Assert that all the terms in the needles list are found in the haystack.

    :param test_case: The ``TestCase`` instance on which to call assertions.
    :param list needles: A list of terms to search for in the ``haystack``.
    :param haystack: An iterable in which to search for the terms in needles.
    """
    for needle in reversed(needles):
        if needle in haystack:
            needles.remove(needle)

    if needles:
        test_case.fail(
            '{haystack} did not contain {needles}'.format(
                haystack=haystack, needles=needles
            )
        )


# Skip decorators for tests:
if_root = skipIf(os.getuid() != 0, "Must run as root.")
not_root = skipIf(os.getuid() == 0, "Must not run as root.")


# TODO: This should be provided by Twisted (also it should be more complete
# instead of 1/3rd done).
from twisted.internet.base import _ThreePhaseEvent


@implementer(IReactorCore)
class MemoryCoreReactor(MemoryReactor, Clock):
    """
    Fake reactor with listenTCP, IReactorTime and just enough of an
    implementation of IReactorCore.
    """
    def __init__(self):
        MemoryReactor.__init__(self)
        Clock.__init__(self)
        self._triggers = {}

    def addSystemEventTrigger(self, phase, eventType, callable, *args, **kw):
        event = self._triggers.setdefault(eventType, _ThreePhaseEvent())
        return eventType, event.addTrigger(phase, callable, *args, **kw)

    def removeSystemEventTrigger(self, triggerID):
        eventType, handle = triggerID
        event = self._triggers.setdefault(eventType, _ThreePhaseEvent())
        event.removeTrigger(handle)

    def fireSystemEvent(self, eventType):
        event = self._triggers.get(eventType)
        if event is not None:
            event.fireEvent()


def make_script_tests(executable):
    """
    Generate a test suite which applies to any Flocker-installed node script.

    :param bytes executable: The basename of the script to be tested.

    :return: A ``TestCase`` subclass which defines some tests applied to the
        given executable.
    """
    class ScriptTests(TestCase):
        @skipUnless(which(executable), executable + " not installed")
        def test_version(self):
            """
            The script is a command available on the system path.
            """
            result = run_process([executable] + [b"--version"])
            self.assertEqual(result.output, b"%s\n" % (__version__,))

        @skipUnless(which(executable), executable + " not installed")
        def test_identification(self):
            """
            The script identifies itself as what it is.
            """
            result = run_process([executable] + [b"--help"])
            self.assertIn(executable, result.output)
    return ScriptTests


class FakeAMPClient(object):
    """
    Emulate an AMP client's ability to send commands.

    A minimal amount of validation is done on registered responses and sent
    requests, but this should not be relied upon.

    :ivar list calls: ``(command, kwargs)`` tuples of commands that have
        been sent using ``callRemote``.
    """

    def __init__(self):
        self._responses = {}
        self.calls = []

    def _makeKey(self, command, kwargs):
        """
        Create a key for the responses dictionary.

        @param commandType: a subclass of C{amp.Command}.

        @param kwargs: a dictionary.

        @return: A value that can be used as a dictionary key.
        """
        return (command, tuple(sorted(kwargs.items())))

    def register_response(self, command, kwargs, response):
        """
        Register a response to a L{callRemote} command.

        @param commandType: a subclass of C{amp.Command}.

        @param kwargs: Keyword arguments taken by the command, a C{dict}.

        @param response: The response to the command.
        """
        try:
            command.makeResponse(response, AMP())
        except KeyError:
            raise InvalidSignature("Bad registered response")
        self._responses[self._makeKey(command, kwargs)] = response

    def callRemote(self, command, **kwargs):
        """
        Return a previously registered response.

        @param commandType: a subclass of C{amp.Command}.

        @param kwargs: Keyword arguments taken by the command, a C{dict}.

        @return: A C{Deferred} that fires with the registered response for
            this particular combination of command and arguments.
        """
        self.calls.append((command, kwargs))
        command.makeArguments(kwargs, AMP())
        # if an eliot_context is present, disregard it, because we cannot
        # reliably determine this in advance in order to include it in the
        # response register
        if 'eliot_context' in kwargs:
            kwargs.pop('eliot_context')
        return succeed(self._responses[self._makeKey(command, kwargs)])


class CustomException(Exception):
    """
    An exception that will never be raised by real code, useful for
    testing.
    """


TWISTED_CHILD_PROCESS_ACTION = ActionType(
    u'flocker:testtools:logged_run_process',
    fields(command=list),
    [],
    u'A child process is spawned using Twisted',
)

STDOUT_RECEIVED = MessageType(
    u'flocker:testtools:logged_run_process:stdout',
    fields(output=str),
    u'A chunk of stdout received from a child process',
)

STDERR_RECEIVED = MessageType(
    u'flocker:testtools:logged_run_process:stdout',
    fields(output=str),
    u'A chunk of stderr received from a child process',
)

PROCESS_ENDED = MessageType(
    u'flocker:testtools:logged_run_process:process_ended',
    fields(status=int),
    u'The process terminated')


class _ProcessResult(PRecord):
    """
    The return type for ``run_process`` representing the outcome of the process
    that was run.
    """
    command = field(type=list, mandatory=True)
    output = field(type=bytes, mandatory=True)
    status = field(type=int, mandatory=True)


class _CalledProcessError(CalledProcessError):
    """
    Just like ``CalledProcessError`` except output is included in the string
    representation.
    """
    def __str__(self):
        base = super(_CalledProcessError, self).__str__()
        lines = "\n".join("    |" + line for line in self.output.splitlines())
        return base + " and output:\n" + lines


class _LoggingProcessProtocol(ProcessProtocol):
    """
    A ``ProcessProtocol`` that both stores and logs output from the
    subprocess. Output is logged as it is received.

    Intended to be used by ``logged_run_process``.
    """

    def __init__(self, deferred, action):
        """
        Construct a ``_LoggingProcessProtocol``.

        :param deferred: A ``Deferred`` that will fire with
            ``(reason, output)``
            when the process ends, where ``reason`` is a ``Failure`` with the
            reason for the process ending (see ``IProcessProtocol``), and
            ``output`` are the bytes outputted by the process (both to stdout
            and stderr).
        :param action: The Eliot ``Action`` under which this process is being
            run.
        """
        self._deferred = deferred
        self._action = action
        self._output_buffer = StringIO()

    def outReceived(self, data):
        with self._action.context():
            self._output_buffer.write(data)
            STDOUT_RECEIVED(output=data).write()

    def errReceived(self, data):
        with self._action.context():
            self._output_buffer.write(data)
            STDERR_RECEIVED(output=data).write()

    def processExited(self, reason):
        with self._action.context():
            PROCESS_ENDED(status=reason.value.status).write()
            self._deferred.callback((reason, self._output_buffer.getvalue()))


def logged_run_process(reactor, command):
    """
    Run a child process, and log the output as we get it.

    :param reactor: An ``IReactorProcess`` to spawn the process on.
    :param command: An argument list specifying the child process to run.

    :return: A ``Deferred`` that calls back with ``_ProcessResult`` if the
        process exited successfully, or errbacks with
        ``_CalledProcessError`` otherwise.
    """
    d = Deferred()
    action = TWISTED_CHILD_PROCESS_ACTION(command=command)
    with action.context():
        d2 = DeferredContext(d)
        protocol = _LoggingProcessProtocol(d, action)
        reactor.spawnProcess(protocol, command[0], command)

        def process_ended((reason, output)):
            status = reason.value.status
            if status:
                raise _CalledProcessError(
                    returncode=status, cmd=command, output=output)
            return _ProcessResult(
                command=command,
                status=status,
                output=output,
            )

        d2.addCallback(process_ended)
        d2.addActionFinish()
        return d2.result


def run_process(command, *args, **kwargs):
    """
    Run a child process, capturing its stdout and stderr.

    :param list command: An argument list to use to launch the child process.

    :raise CalledProcessError: If the child process has a non-zero exit status.

    :return: A ``_ProcessResult`` instance describing the result of the child
         process.
    """
    kwargs["stdout"] = PIPE
    kwargs["stderr"] = STDOUT
    action = start_action(
        action_type="run_process", command=command, args=args, kwargs=kwargs)
    with action:
        process = Popen(command, *args, **kwargs)
        output = process.stdout.read()
        status = process.wait()
        result = _ProcessResult(command=command, output=output, status=status)
        # TODO: We should be using a specific logging type for this.
        Message.new(
            command=result.command,
            output=result.output,
            status=result.status,
        ).write()
        if result.status:
            raise _CalledProcessError(
                returncode=status, cmd=command, output=output,
            )
    return result


def skip_except(supported_tests):
    """
    Mark all the ``test_`` methods in ``TestCase`` as ``skip`` unless the test
    method names are in ``supported_tests``.

    :param list supported_tests: The names of the tests that are expected to
        pass.
    """
    test_prefix = 'test_'
    skip_or_todo = 'skip'
    noskip = os.environ.get('NOSKIP')
    if noskip is not None:
        return lambda test_case: test_case

    def decorator(test_case):
        test_method_names = [
            test_prefix + name
            for name
            in prefixedMethodNames(test_case, test_prefix)
        ]
        for test_method_name in test_method_names:
            if test_method_name not in supported_tests:
                test_method = getattr(test_case, test_method_name)
                new_message = []
                existing_message = getattr(test_method, skip_or_todo, None)
                if existing_message is not None:
                    new_message.append(existing_message)
                new_message.append('Not implemented yet')
                new_message = ' '.join(new_message)

                @wraps(test_method)
                def wrapper(*args, **kwargs):
                    return test_method(*args, **kwargs)
                setattr(wrapper, skip_or_todo, new_message)
                setattr(test_case, test_method_name, wrapper)

        return test_case
    return decorator
