# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Helpers for flocker shell commands."""

import sys

from bitmath import MiB

from eliot import MessageType, fields, Logger
from eliot.logwriter import ThreadedFileWriter

from twisted.application.service import MultiService, Service
from twisted.internet import task, reactor as global_reactor
from twisted.internet.defer import Deferred, maybeDeferred
from twisted.python import usage
from twisted.python.log import textFromEventDict, startLoggingWithObserver, err
from twisted.python import log as twisted_log
from twisted.python.logfile import LogFile
from twisted.python.filepath import FilePath

from zope.interface import Interface

from .. import __version__


__all__ = [
    'flocker_standard_options',
    'ICommandLineScript',
    'FlockerScriptRunner',
    'main_for_service',
]


LOGFILE_LENGTH = int(MiB(100).to_Byte().value)
LOGFILE_COUNT = 5


def flocker_standard_options(cls):
    """Add various standard command line options to flocker commands.

    :param type cls: The `class` to decorate.
    :return: The decorated `class`.
    """
    original_init = cls.__init__

    def __init__(self, *args, **kwargs):
        """Set the default verbosity to `0`

        Calls the original ``cls.__init__`` method finally.

        :param sys_module: An optional ``sys`` like module for use in
            testing. Defaults to ``sys``.
        """
        self._sys_module = kwargs.pop('sys_module', sys)
        self['verbosity'] = 0
        self['logfile'] = self._sys_module.stdout
        original_init(self, *args, **kwargs)
    cls.__init__ = __init__

    def opt_version(self):
        """Print the program's version and exit."""
        self._sys_module.stdout.write(__version__.encode('utf-8') + b'\n')
        raise SystemExit(0)
    cls.opt_version = opt_version

    def opt_verbose(self):
        """Turn on verbose logging."""
        self['verbosity'] += 1
    cls.opt_verbose = opt_verbose
    cls.opt_v = opt_verbose

    def opt_logfile(self, logfile_path):
        """
        Log to a file. Log is written to ``stdout`` by default. The logfile
        directory is created if it does not already exist.
        """
        logfile = FilePath(logfile_path)
        logfile_directory = logfile.parent()
        if not logfile_directory.exists():
            logfile_directory.makedirs()
        self['logfile'] = LogFile.fromFullPath(
            logfile.path,
            rotateLength=LOGFILE_LENGTH,
            maxRotatedFiles=LOGFILE_COUNT,
        )
    cls.opt_logfile = opt_logfile

    return cls


class ICommandLineScript(Interface):
    """A script which can be run by ``FlockerScriptRunner``."""
    def main(reactor, options):
        """
        :param reactor: A Twisted reactor.
        :param dict options: A dictionary of configuration options.
        :return: A ``Deferred`` which fires when the script has completed.
        """


def eliot_logging_service(log_file, reactor, capture_stdout):
    service = MultiService()
    ThreadedFileWriter(log_file, reactor).setServiceParent(service)
    EliotObserver(capture_stdout=capture_stdout).setServiceParent(service)
    return service


# This should probably be built-in functionality in Eliot;
# see https://github.com/ClusterHQ/eliot/issues/143
TWISTED_LOG_MESSAGE = MessageType("twisted:log",
                                  fields(error=bool, message=unicode),
                                  u"A log message from Twisted.")


class EliotObserver(Service):
    """
    A Twisted log observer that logs to Eliot.
    """
    def __init__(self, publisher=twisted_log, capture_stdout=True):
        """
        :param publisher: A ``LogPublisher`` to capture logs from, or if no
            argument is given the default Twisted log system.
        :param bool capture_stdout: Wether to capture standard output and
            standard error to eliot.
        """
        self.logger = Logger()
        self.publisher = publisher
        self.capture_stdout = capture_stdout

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
        startLoggingWithObserver(self, setStdout=self.capture_stdout)


class FlockerScriptRunner(object):
    """An API for running standard flocker scripts.

    :ivar ICommandLineScript script: See ``script`` of ``__init__``.
    :ivar _react: A reference to ``task.react`` which can be overridden for
        testing purposes.
    """
    _react = staticmethod(task.react)

    def __init__(self, script, options, logging=True,
                 reactor=None, sys_module=None):
        """
        :param ICommandLineScript script: The script object to be run.
        :param usage.Options options: An option parser object.
        :param logging: If ``True``, log to stdout; otherwise don't log.
        :param reactor: Optional reactor to override default one.
        :param sys_module: An optional ``sys`` like module for use in
            testing. Defaults to ``sys``.
        """
        self.script = script
        self.options = options
        self.logging = logging
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
            self.options.parseOptions(arguments)
        except usage.UsageError as e:
            self.sys_module.stderr.write(unicode(self.options).encode('utf-8'))
            self.sys_module.stderr.write(
                b'ERROR: ' + e.message.encode('utf-8') + b'\n')
            raise SystemExit(1)
        return self.options

    def main(self):
        """Parse arguments and run the script's main function via ``react``."""
        # If e.g. --version is called this may throw a SystemExit, so we
        # always do this first before any side-effecty code is run:
        options = self._parse_options(self.sys_module.argv[1:])

        if self.logging:
            log_writer = eliot_logging_service(
                options['logfile'], self._reactor, True)
        else:
            log_writer = Service()
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
