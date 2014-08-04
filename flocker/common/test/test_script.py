# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Tests for :module:`flocker.common.script`."""

import sys
from os import getpid

from twisted.internet import task
from twisted.internet.defer import succeed
from twisted.python import usage
from twisted.trial.unittest import SynchronousTestCase
from twisted.python.filepath import FilePath
from twisted.python.log import msg

from ..script import flocker_standard_options, FlockerScriptRunner
from ...testtools import (
    help_problems, FakeSysModule, StandardOptionsTestsMixin,
    skip_on_broken_permissions, attempt_effective_uid,
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
                                     reactor=fakeReactor, sys_module=sys)

        self.assertRaises(SystemExit, runner.main)
        self.assertEqual(b"world", script.arguments.value)


class LoggingScript(object):
    """
    Log a message.
    """
    def main(self, *args, **kwargs):
        msg("it's alive")
        return succeed(None)


class FlockerScriptRunnerLoggingTests(SynchronousTestCase):
    """
    Tests for :py:class:`FlockerScriptRunner` logging."""

    def test_adds_log_observer(self):
        """
        ``FlockerScriptRunner.main`` logs to the given directory using a
        filename composed of process name and pid.
        """
        options = usage.Options()
        sys = FakeSysModule(argv=[b"/usr/bin/mythingie"])
        logs = FilePath(self.mktemp())
        runner = FlockerScriptRunner(LoggingScript(), options, reactor=None,
                                     sys_module=sys)
        runner.log_directory = logs
        try:
            runner.main()
        except SystemExit:
            pass
        path = logs.child(b"mythingie-%d.log" % (getpid(),))
        self.assertIn(b"it's alive", path.getContent())

    def test_logs_arguments(self):
        """
        ``FlockerScriptRunner.main`` logs ``self.sys_module.argv``.
        """
        options = usage.Options()
        sys = FakeSysModule(argv=[b"mythingie", b"--version"])
        logs = FilePath(self.mktemp())
        runner = FlockerScriptRunner(LoggingScript(), options, reactor=None,
                                     sys_module=sys)
        runner.log_directory = logs
        try:
            runner.main()
        except SystemExit:
            pass
        path = logs.child(b"mythingie-%d.log" % (getpid(),))
        self.assertIn(b"--version", path.getContent())

    def test_default_log_directory(self):
        """
        ``FlockerScriptRunner.main`` logs to ``/var/log/flocker/`` by default.
        """
        runner = FlockerScriptRunner(None, None)
        self.assertEqual(runner.log_directory, FilePath(b"/var/log/flocker"))

    @skip_on_broken_permissions
    def test_no_logging_if_permission_denied(self):
        """
        If there is no permission to write to the given directory this does
        not prevent the script from running.
        """
        options = usage.Options()
        sys = FakeSysModule(argv=[b"mythingie"])
        logs = FilePath(self.mktemp())
        logs.makedirs()
        logs.chmod(0)
        self.addCleanup(logs.chmod, 0o777)

        class Script(object):
            ran = False

            def main(self, *args, **kwargs):
                self.ran = True
                return succeed(None)

        script = Script()
        from twisted.test.test_task import _FakeReactor
        fakeReactor = _FakeReactor()
        runner = FlockerScriptRunner(script, options, reactor=fakeReactor,
                                     sys_module=sys)
        runner.log_directory = logs
        try:
            with attempt_effective_uid('nobody', suppress_errors=True):
                runner.main()
        except SystemExit:
            pass
        self.assertTrue(script.ran)


@flocker_standard_options
class TestOptions(usage.Options):
    """An unmodified ``usage.Options`` subclass for use in testing."""


class FlockerStandardOptionsTests(StandardOptionsTestsMixin,
                                  SynchronousTestCase):
    """Tests for ``flocker_standard_options``

    Using a decorating an unmodified ``usage.Options`` subclass.
    """
    options = TestOptions
