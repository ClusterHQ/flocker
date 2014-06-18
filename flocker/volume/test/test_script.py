# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Tests for :module:`flocker.volume.script`."""

import io, sys

from twisted.internet.defer import succeed
from twisted.trial.unittest import SynchronousTestCase
from twisted.python.filepath import FilePath
from twisted.python import usage

from ..script import (
    flocker_standard_options, FlockerVolumeOptions, FlockerScriptRunner,
    VolumeScript)

from ... import __version__


def helpProblems(commandName, helpText):
    """
    Identify and return a list of problems with the help output for a given
    command.
    """
    problems = []
    expectedStart = b'Usage: {command}'.format(command=commandName)
    if not helpText.startswith(expectedStart):
        problems.append(
            'Does not begin with {expected}. Found {actual} instead'.format(
                expected=repr(expectedStart),
                actual=repr(helpText[:len(expectedStart)])
            )
        )
    return problems



class FlockerScriptRunnerTests(SynchronousTestCase):
    """
    Tests for :class:`FlockerScriptRunner`.
    """
    def test_parseOptions(self):
        """
        ``FlockerScriptRunner._parseOptions`` accepts a list of arguments,
        instantiates a ``usage.Options`` instance using the the ``options``
        factory of the supplied script and calls its `parseOptions` method with
        the supplied arguments and returns the populated options instance.
        """
        class OptionsSpy(usage.Options):
            def parseOptions(self, arguments):
                self.parseOptionsArguments = arguments

        class FakeScript(object):
            options = OptionsSpy

        expectedArguments = [object(), object()]
        runner = FlockerScriptRunner(script=FakeScript)
        options = runner._parseOptions(expectedArguments)
        self.assertEqual(expectedArguments, options.parseOptionsArguments)


    def test_parseOptionsUsageError(self):
        """
        `FlockerScriptRunner._parseOptions` catches `usage.UsageError`
        exceptions and writes the help text and an error message to `stderr`
        before exiting with status 1.
        """
        expectedMessage = b'foo bar baz'
        expectedCommandName = b'test_command'
        class FakeOptions(usage.Options):
            synopsis = 'Usage: %s [options]' % (expectedCommandName,)
            def parseOptions(self, arguments):
                raise usage.UsageError(expectedMessage)


        class FakeScript(object):
            options = FakeOptions

        sys = FakeSysModule()

        runner = FlockerScriptRunner(script=FakeScript, sys_module=sys)
        error = self.assertRaises(SystemExit, runner._parseOptions, [])
        expectedErrorMessage = b'ERROR: %s\n' % (expectedMessage,)
        errorText = sys.stderr.getvalue()
        self.assertEqual(
            (1, [], expectedErrorMessage),
            (error.code, helpProblems('test_command', errorText), errorText[-len(expectedErrorMessage):])
        )



class FakeSysModule(object):
    """
    """
    def __init__(self, expected_argv=None):
        if expected_argv is None:
            expected_argv = []
        self.argv = expected_argv
        # io.BytesIO is not quite the same as sys.stdout/stderr
        # particularly with respect to unicode handling.  So,
        # hopefully the implementation doesn't try to write any
        # unicode.
        self.stdout = io.BytesIO()
        self.stderr = io.BytesIO()



class FlockerScriptRunnerMainTests(SynchronousTestCase):
    """
    """
    def test_sys_default(self):
        """
        `FlockerScriptRunner.sys` is `sys` by default.
        """
        self.assertIs(
            sys,
            FlockerScriptRunner(script=None).sys_module
        )


    def test_sys_override(self):
        """
        `FlockerScriptRunner.sys` can be overridden in the constructor.
        """
        dummySys = object()
        self.assertIs(
            dummySys,
            FlockerScriptRunner(script=None, sys_module=dummySys).sys_module
        )


    def test_main_uses_sysargv_by_default(self):
        """
        ``FlockerScriptRunner.main`` uses ``sys.argv`` by default.
        """
        expectedArgv = [b"flocker", b"--hello", b"world"]

        class SillyOptions(usage.Options):
            def opt_hello(self, value):
                self.value = value

        class SpyScript(object):
            def options(self, stdout, stderr):
                return SillyOptions()

            def main(self, reactor, stdout, stderr, arguments):
                self.arguments = arguments
                return succeed(None)

        script = SpyScript()
        sys = FakeSysModule(expectedArgv)

        runner = FlockerScriptRunner(
            script=script,
            sys_module=sys,
        )

        self.assertRaises(SystemExit, runner.main)

        self.assertEqual(b"world", script.arguments.value)


    def xtest_main(self):
        """
        `FlockerScriptRunner.main` accepts an `arguments` argument which is
        passed to `FlockerScriptRunner._parseOptions` and which is
        `sys.argv[1:]` by default.
        """
        class FakeScript(object):
            def main(self, reactor, arguments):
                pass

        expectedScriptInstance = FakeScript()
        runner = FlockerScriptRunner(
            script=lambda stdout, stderr: expectedScriptInstance,
            stdout=object(),
            stderr=object()
        )

        expectedOptionsObject = object()
        parseOptionsArguments = []
        def fakeParseOptions(arguments):
            parseOptionsArguments.append(arguments)
            return expectedOptionsObject

        self.patch(runner, '_parseOptions', fakeParseOptions)

        reactArguments = []
        self.patch(
            runner,
            '_react',
            lambda mainFunction, argv: reactArguments.append(
                (mainFunction, argv))
        )

        defaultArguments = [None, object()]
        self.patch(sys, 'argv', defaultArguments)
        runner.main()

        explicitArguments = [object()]
        runner.main(arguments=explicitArguments)

        expectedParseOptionsArguments = [
            defaultArguments[1:],
            explicitArguments
        ]

        expectedReactArguments = [
            (expectedScriptInstance.main, expectedOptionsObject),
            (expectedScriptInstance.main, expectedOptionsObject),
        ]

        self.assertEqual(
            (expectedParseOptionsArguments, expectedReactArguments),
            (parseOptionsArguments, reactArguments)
        )



class FlockerScriptTestsMixin(object):
    """
    Common tests for scripts that can be run via L{FlockerScriptRunner}
    """
    script = None
    script_name = None

    def test_incorrect_arguments(self):
        """
        L{FlockerScript.main} exits with status 0 and prints help to stderr if
        supplied with unexpected arguments.
        """
        sys = FakeSysModule()
        script = FlockerScriptRunner(self.script, sys_module=sys)
        error = self.assertRaises(
            SystemExit,
            script.main,
            b'--unexpected-argument'
        )
        error_text = sys.stderr.getvalue()
        self.assertEqual(
            (1, []),
            (error.code, helpProblems(self.script_name, error_text))
        )



class VolumeScriptTests(FlockerScriptTestsMixin, SynchronousTestCase):
    """
    Tests for L{VolumeScript}.
    """
    script = VolumeScript
    script_name = 'flocker-volume'



class StandardOptionsTestsMixin(object):
    """
    Tests for the standard options that should be available on every flocker
    command.
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
        Flocker commands have a I{--version} option which prints the current
        version string to stdout and causes the command to exit with status 0.
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
        Flocker commands have C{verbosity} of C{0} by default.
        """
        options = self.options()
        self.assertEqual(0, options['verbosity'])


    def test_verbosity_option(self):
        """
        Flocker commands have a I{--verbose} option which increments the
        configured verbosity by 1.
        """
        options = self.options()
        options.parseOptions(['--verbose'])
        self.assertEqual(1, options['verbosity'])


    def test_verbosity_option_short(self):
        """
        Flocker commands have a I{-v} option which increments the configured
        verbosity by 1.
        """
        options = self.options()
        options.parseOptions(['-v'])
        self.assertEqual(1, options['verbosity'])


    def test_verbosity_multiple(self):
        """
        I{--verbose} can be supplied multiple times to increase the verbosity.
        """
        options = self.options()
        options.parseOptions(['-v', '--verbose'])
        self.assertEqual(2, options['verbosity'])



class FlockerStandardOptionsTests(StandardOptionsTestsMixin,
                                  SynchronousTestCase):
    """
    """
    def options(self, **kwargs):
        """
        """
        @flocker_standard_options
        class TestOptions(usage.Options):
            pass
        return TestOptions(**kwargs)



class FlockerVolumeOptionsTests(StandardOptionsTestsMixin, SynchronousTestCase):
    """Tests for :class:`FlockerVolumeOptions`."""
    options = FlockerVolumeOptions

    def test_default_config(self):
        """By default the config file is ``b'/etc/flocker/volume.json'``."""
        options = self.options()
        options.parseOptions([])
        self.assertEqual(options["config"],
                         FilePath(b"/etc/flocker/volume.json"))

    def test_custom_config(self):
        """A custom config file can be specified with ``--config``."""
        options = self.options()
        options.parseOptions([b"--config", b"/path/somefile.json"])
        self.assertEqual(options["config"],
                         FilePath(b"/path/somefile.json"))
