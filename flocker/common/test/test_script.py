# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Tests for :module:`flocker.common.script`."""

import sys

from eliot.testing import validateLogging, assertHasMessage

from twisted.internet import task
from twisted.internet.defer import succeed
from twisted.python import usage
from twisted.trial.unittest import SynchronousTestCase
from twisted.python.failure import Failure
from twisted.python.log import LogPublisher
from twisted.python import log as twisted_log
from twisted.internet.defer import Deferred
from twisted.application.service import Service

from ..script import (
    flocker_standard_options, FlockerScriptRunner, main_for_service,
    EliotObserver, TWISTED_LOG_MESSAGE,
    )
from ...testtools import (
    help_problems, FakeSysModule, StandardOptionsTestsMixin,
    MemoryCoreReactor,
    )


class FlockerScriptRunnerInitTests(SynchronousTestCase):
    """Tests for :py:meth:`FlockerScriptRunner.__init__`."""

    def test_sys_default(self):
        """
        `FlockerScriptRunner.sys` is `sys` by default.
        """
        self.assertIs(
            sys,
            FlockerScriptRunner(
                script=None, options=None).sys_module
        )

    def test_sys_override(self):
        """
        `FlockerScriptRunner.sys` can be overridden in the constructor.
        """
        dummySys = object()
        self.assertIs(
            dummySys,
            FlockerScriptRunner(script=None, options=None,
                                sys_module=dummySys).sys_module
        )

    def test_react(self):
        """
        `FlockerScriptRunner._react` is ``task.react`` by default
        """
        self.assertIs(
            task.react,
            FlockerScriptRunner(script=None, options=None)._react
        )


class FlockerScriptRunnerParseOptionsTests(SynchronousTestCase):
    """Tests for :py:meth:`FlockerScriptRunner._parse_options`."""

    def test_parse_options(self):
        """
        ``FlockerScriptRunner._parse_options`` accepts a list of arguments,
        passes them to the `parseOptions` method of its ``options`` attribute
        and returns the populated options instance.
        """
        class OptionsSpy(usage.Options):
            def parseOptions(self, arguments):
                self.parseOptionsArguments = arguments

        expectedArguments = [object(), object()]
        runner = FlockerScriptRunner(script=None, options=OptionsSpy())
        options = runner._parse_options(expectedArguments)
        self.assertEqual(expectedArguments, options.parseOptionsArguments)

    def test_parse_options_usage_error(self):
        """
        `FlockerScriptRunner._parse_options` catches `usage.UsageError`
        exceptions and writes the help text and an error message to `stderr`
        before exiting with status 1.
        """
        expectedMessage = b'foo bar baz'
        expectedCommandName = b'test_command'

        class FakeOptions(usage.Options):
            synopsis = 'Usage: %s [options]' % (expectedCommandName,)

            def parseOptions(self, arguments):
                raise usage.UsageError(expectedMessage)

        fake_sys = FakeSysModule()

        runner = FlockerScriptRunner(script=None, options=FakeOptions(),
                                     sys_module=fake_sys)
        error = self.assertRaises(SystemExit, runner._parse_options, [])
        expectedErrorMessage = b'ERROR: %s\n' % (expectedMessage,)
        errorText = fake_sys.stderr.getvalue()
        self.assertEqual(
            (1, [], expectedErrorMessage),
            (error.code,
             help_problems(u'test_command', errorText),
             errorText[-len(expectedErrorMessage):])
        )


class FlockerScriptRunnerMainTests(SynchronousTestCase):
    """Tests for :py:meth:`FlockerScriptRunner.main`."""

    def test_main_uses_sysargv(self):
        """
        ``FlockerScriptRunner.main`` uses ``self.sys_module.argv``.
        """
        class SpyOptions(usage.Options):
            def opt_hello(self, value):
                self.value = value

        class SpyScript(object):
            def main(self, reactor, arguments):
                self.reactor = reactor
                self.arguments = arguments
                return succeed(None)

        options = SpyOptions()
        script = SpyScript()
        sys = FakeSysModule(argv=[b"flocker", b"--hello", b"world"])
        # XXX: We shouldn't be using this private fake and Twisted probably
        # shouldn't either. See https://twistedmatrix.com/trac/ticket/6200 and
        # https://twistedmatrix.com/trac/ticket/7527
        from twisted.test.test_task import _FakeReactor
        fakeReactor = _FakeReactor()
        runner = FlockerScriptRunner(script, options,
                                     reactor=fakeReactor, sys_module=sys,
                                     logging=False)
        self.assertRaises(SystemExit, runner.main)
        self.assertEqual(b"world", script.arguments.value)

    def test_disabled_logging(self):
        """
        If ``logging`` is set to ``False``, ``FlockerScriptRunner.main``
        does not log to ``sys.stdout``.
        """
        class Script(object):
            def main(self, reactor, arguments):
                twisted_log.msg(b"hello!")
                return succeed(None)

        script = Script()
        sys = FakeSysModule(argv=[])
        # XXX: We shouldn't be using this private fake and Twisted probably
        # shouldn't either. See https://twistedmatrix.com/trac/ticket/6200 and
        # https://twistedmatrix.com/trac/ticket/7527
        from twisted.test.test_task import _FakeReactor
        fakeReactor = _FakeReactor()
        runner = FlockerScriptRunner(script, usage.Options(),
                                     reactor=fakeReactor, sys_module=sys,
                                     logging=False)
        self.assertRaises(SystemExit, runner.main)
        self.assertEqual(sys.stdout.getvalue(), b"")


@flocker_standard_options
class TestOptions(usage.Options):
    """An unmodified ``usage.Options`` subclass for use in testing."""


class FlockerStandardOptionsTests(StandardOptionsTestsMixin,
                                  SynchronousTestCase):
    """Tests for ``flocker_standard_options``

    Using a decorating an unmodified ``usage.Options`` subclass.
    """
    options = TestOptions


class AsyncStopService(Service):
    """
    An ``IService`` implementation which can return an unfired ``Deferred``
    from its ``stopService`` method.

    :ivar Deferred stop_result: The object to return from ``stopService``.
        ``AsyncStopService`` won't do anything more than return it.  If it is
        ever going to fire, some external code is responsible for firing it.
    """
    def __init__(self, stop_result):
        self.stop_result = stop_result

    def stopService(self):
        Service.stopService(self)
        return self.stop_result


class MainForServiceTests(SynchronousTestCase):
    """
    Tests for ``main_for_service``.
    """
    def setUp(self):
        self.reactor = MemoryCoreReactor()
        self.service = Service()

    def _shutdown_reactor(self, reactor):
        """
        Simulate reactor shutdown.

        :param IReactorCore reactor: The reactor to shut down.
        """
        reactor.fireSystemEvent("shutdown")

    def test_starts_service(self):
        """
        ``main_for_service`` accepts an ``IService`` provider and starts it.
        """
        main_for_service(self.reactor, self.service)
        self.assertTrue(
            self.service.running, "The service should have been started.")

    def test_returns_unfired_deferred(self):
        """
        ``main_for_service`` returns a ``Deferred`` which has not fired.
        """
        result = main_for_service(self.reactor, self.service)
        self.assertNoResult(result)

    def test_fire_on_stop(self):
        """
        The ``Deferred`` returned by ``main_for_service`` fires with ``None``
        when the reactor is stopped.
        """
        result = main_for_service(self.reactor, self.service)
        self._shutdown_reactor(self.reactor)
        self.assertIs(None, self.successResultOf(result))

    def test_stops_service(self):
        """
        When the reactor is stopped, ``main_for_service`` stops the service it
        was called with.
        """
        main_for_service(self.reactor, self.service)
        self._shutdown_reactor(self.reactor)
        self.assertFalse(
            self.service.running, "The service should have been stopped.")

    def test_wait_for_service_stop(self):
        """
        The ``Deferred`` returned by ``main_for_service`` does not fire before
        the ``Deferred`` returned by the service's ``stopService`` method
        fires.
        """
        result = main_for_service(self.reactor, AsyncStopService(Deferred()))
        self._shutdown_reactor(self.reactor)
        self.assertNoResult(result)

    def test_fire_after_service_stop(self):
        """
        The ``Deferred`` returned by ``main_for_service`` fires once the
        ``Deferred`` returned by the service's ``stopService`` method fires.
        """
        async = Deferred()
        result = main_for_service(self.reactor, AsyncStopService(async))
        self._shutdown_reactor(self.reactor)
        async.callback(None)
        self.assertIs(None, self.successResultOf(result))


class EliotObserverTests(SynchronousTestCase):
    """
    Tests for ``EliotObserver``.
    """
    @validateLogging(None)
    def test_message(self, logger):
        """
        A message logged to the given ``LogPublisher`` is converted to an
        Eliot log message.
        """
        publisher = LogPublisher()
        observer = EliotObserver(publisher)
        observer.logger = logger
        publisher.addObserver(observer)
        publisher.msg(b"Hello", b"world")
        assertHasMessage(self, logger, TWISTED_LOG_MESSAGE,
                         dict(error=False, message=u"Hello world"))

    @validateLogging(None)
    def test_error(self, logger):
        """
        An error logged to the given ``LogPublisher`` is converted to an Eliot
        log message.
        """
        publisher = LogPublisher()
        observer = EliotObserver(publisher)
        observer.logger = logger
        publisher.addObserver(observer)
        # No public API for this unfortunately, so emulate error logging:
        publisher.msg(failure=Failure(ZeroDivisionError("onoes")),
                      why=b"A zero division ono",
                      isError=True)
        message = (u'A zero division ono\nTraceback (most recent call '
                   u'last):\nFailure: exceptions.ZeroDivisionError: onoes\n')
        assertHasMessage(self, logger, TWISTED_LOG_MESSAGE,
                         dict(error=True, message=message))
