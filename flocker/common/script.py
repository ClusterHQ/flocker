# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.common.test.test_script -*-

"""Helpers for flocker shell commands."""

import os
import sys

from pyrsistent import PRecord, field

from eliot import MessageType, fields, Logger
from eliot.logwriter import ThreadedFileWriter

from twisted.application.service import Service, MultiService
from twisted.internet import task, reactor as global_reactor
from twisted.internet.defer import Deferred, maybeDeferred
from twisted.python import usage
from twisted.python.filepath import FilePath
from twisted.python.log import textFromEventDict, startLoggingWithObserver, err
from twisted.python import log as twisted_log

from zope.interface import Interface, implementer

from .. import __version__

from appdirs import AppDirs

__all__ = [
    'ICommandLineScript',
    'FlockerScriptRunner',
    'main_for_service',
]


def _flocker_standard_options(cls):
    """Add various standard command line options to flocker commands.

    :param type cls: The `class` to decorate.
    :return: The decorated `class`.
    """
    class FlockerStandardOptions(cls):

        def __init__(self, *args, **kwargs):
            """Set the default verbosity to `0`

            Calls the original ``cls.__init__`` method finally.

            :param sys_module: An optional ``sys`` like module for use in
                testing. Defaults to ``sys``.
            """
            self._sys_module = kwargs.pop('sys_module', sys)
            cls.__init__(self, *args, **kwargs)

        def opt_version(self):
            """Print the program's version and exit."""
            self._sys_module.stdout.write(__version__.encode('utf-8') + b'\n')
            raise SystemExit(0)

    return FlockerStandardOptions


class ICommandLineScript(Interface):
    """A script which can be run by ``FlockerScriptRunner``."""
    def main(reactor, options):
        """
        :param reactor: A Twisted reactor.
        :param dict options: A dictionary of configuration options.
        :return: A ``Deferred`` which fires when the script has completed.
        """


def eliot_logging_service(log_file, reactor, set_stdout):
    service = MultiService()
    ThreadedFileWriter(log_file, reactor).setServiceParent(service)
    EliotObserver(set_stdout=set_stdout).setServiceParent(service)
    return service


class ILoggingPolicy(Interface):
    """
    Logging policy for flocker commans.
    """
    def service(reactor, options):
        """
        Get a service that controls logging.

        :param reactor: Reactor to use.

        :return IService:
        """

    def options_wrapper(cls):
        """
        """


@implementer(ILoggingPolicy)
class StdoutLoggingPolicy(PRecord):
    """
    Logging policy that logs to standard output.

    :ivar sys_module: An optional ``sys`` like module for use in
        testing. Defaults to ``sys``.
    """
    sys_module = field(mandatory=True, initial=sys)

    def service(self, reactor, options):
        return eliot_logging_service(
            self.sys_module.stdout, reactor, set_stdout=True)

    def options_wrapper(self, cls):
        return cls


@implementer(ILoggingPolicy)
class CLILoggingPolicy(PRecord):
    appdirs = field(mandatory=True, initial=AppDirs("Flocker", "ClusterHQ"))
    _getpid = field(mandatory=True, initial=os.getpid)

    def service(self, reactor, options):
        log_dir = FilePath(options['log-dir'])
        log_file = log_dir.child(
            b"%s-%d.log" % (os.path.basename(sys.argv[0]),
                            self._getpid())).open("a")
        return eliot_logging_service(log_file, reactor, set_stdout=False)

    def options_wrapper(self, cls):
        """
        Add standard command line options for logging in CLI commands.

        :param type cls: The `class` to decorate.
        :return: The decorated `class`.
        """
        class FlockerLoggingOptions(cls):
            optParameters = [
                ['log-dir', None, self.appdirs.user_log_dir,
                 "Directory to put log-files in."]]

        return FlockerLoggingOptions


@implementer(ILoggingPolicy)
class NullLoggingPolicy(object):
    def service(self, reactor, options):
        return Service()

    def options_wrapper(self, cls):
        return cls

# This should probably be built-in functionality in Eliot;
# see https://github.com/ClusterHQ/eliot/issues/143
TWISTED_LOG_MESSAGE = MessageType("twisted:log",
                                  fields(error=bool, message=unicode),
                                  u"A log message from Twisted.")


class EliotObserver(Service):
    """
    A Twisted log observer that logs to Eliot.
    """
    def __init__(self, publisher=twisted_log, set_stdout=True):
        """
        :param publisher: A ``LogPublisher`` to capture logs from, or if no
            argument is given the default Twisted log system.
        """
        self.logger = Logger()
        self.publisher = publisher
        self.set_stdout = set_stdout

    def __call__(self, msg):
        error = bool(msg.get("isError"))
        # Twisted log messages on Python 2 are bytes. We don't know the
        # encoding, but assume it's ASCII superset. Charmap will translate
        # ASCII correctly, and higher-bit characters just map to
        # corresponding Unicode code points, and will never fail at decoding.
        message = unicode(textFromEventDict(msg), "charmap")
        TWISTED_LOG_MESSAGE(error=error, message=message).write(self.logger)

    def startService(self):
        """
        Start capturing Twisted logs.
        """
        # We don't bother shutting this down.
        startLoggingWithObserver(self, setStdout=self.set_stdout)


class FlockerScriptRunner(object):
    """An API for running standard flocker scripts.

    :ivar ICommandLineScript script: See ``script`` of ``__init__``.
    :ivar _react: A reference to ``task.react`` which can be overridden for
        testing purposes.
    """
    _react = staticmethod(task.react)

    def __init__(self, script, options, logging_policy,
                 reactor=None, sys_module=None):
        """
        :param ICommandLineScript script: The script object to be run.
        :param type options: ``usage.Options`` subclass.
        :param logging_policy: If ``True``, log to stdout; otherwise don't log.
        :param reactor: Optional reactor to override default one.
        :param sys_module: An optional ``sys`` like module for use in
            testing. Defaults to ``sys``.
        """
        self.script = script
        self.logging_policy = logging_policy
        self.options_class = logging_policy.options_wrapper(
            _flocker_standard_options(options))
        if reactor is None:
            reactor = global_reactor
        self._reactor = reactor

        if sys_module is None:
            sys_module = sys
        self.sys_module = sys_module

    def _parse_options(self, arguments):
        """Parse the options defined in the script's options class.

        ``UsageError``s are caught and printed to `stderr` and the script then
        exits.

        :param list arguments: The command line arguments to be parsed.
        :return: A ``dict`` of configuration options.
        """
        try:
            options = self.options_class()
            options.parseOptions(arguments)
        except usage.UsageError as e:
            self.sys_module.stderr.write(unicode(options).encode('utf-8'))
            self.sys_module.stderr.write(
                b'ERROR: ' + e.message.encode('utf-8') + b'\n')
            raise SystemExit(1)
        return options

    def main(self):
        """Parse arguments and run the script's main function via ``react``."""
        # If e.g. --version is called this may throw a SystemExit, so we
        # always do this first before any side-effecty code is run:
        options = self._parse_options(self.sys_module.argv[1:])

        log_writer = self.logging_policy.service(
            reactor=self._reactor, options=options)
        log_writer.startService()

        # XXX: We shouldn't be using this private _reactor API. See
        # https://twistedmatrix.com/trac/ticket/6200 and
        # https://twistedmatrix.com/trac/ticket/7527
        def run_and_log(reactor):
            d = maybeDeferred(self.script.main, reactor, options)

            def got_error(failure):
                if not failure.check(SystemExit):
                    err(failure)
                return failure
            d.addErrback(got_error)
            return d
        try:
            self._react(run_and_log, [], _reactor=self._reactor)
        finally:
            log_writer.stopService()


def _chain_stop_result(service, stop):
    """
    Stop a service and chain the resulting ``Deferred`` to another
    ``Deferred``.

    :param IService service: The service to stop.
    :param Deferred stop: The ``Deferred`` which will be fired when the service
        has stopped.
    """
    maybeDeferred(service.stopService).chainDeferred(stop)


def main_for_service(reactor, service):
    """
    Start a service and integrate its shutdown with reactor shutdown.

    This is useful for hooking driving an ``IService`` provider with
    ``twisted.internet.task.react``.  For example::

        from twisted.internet.task import react
        from yourapp import YourService
        react(_main_for_service, [YourService()])

    :param IReactorCore reactor: The reactor the run lifetime of which to tie
        to the given service.  When the reactor is shutdown, the service will
        be shutdown.

    :param IService service: The service to tie to the run lifetime of the
        given reactor.  It will be started immediately and made to stop when
        the reactor stops.

    :return: A ``Deferred`` which fires after the service has finished
        stopping.
    """
    service.startService()
    stop = Deferred()
    reactor.addSystemEventTrigger(
        "before", "shutdown", _chain_stop_result, service, stop)
    return stop
