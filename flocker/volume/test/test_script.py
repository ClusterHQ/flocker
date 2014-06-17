# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Tests for :module:`flocker.volume.script`."""

import io, sys

from twisted.trial.unittest import SynchronousTestCase
from twisted.python.filepath import FilePath
from twisted.python import usage

from ..script import FlockerVolumeOptions, FlockerScriptRunner, VolumeScript

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
    def test_stdoutDefault(self):
        """
        `FlockerScriptRunner.stdout` is `sys.stdout` by default.
        """
        self.assertIdentical(
            sys.stdout,
            FlockerScriptRunner(script=object()).stdout
        )


    def test_stdoutOverride(self):
        """
        `FlockerScriptRunner.stdout` can be overridden in the constructor.
        """
        sentinal = object()
        self.assertIdentical(
            sentinal,
            FlockerScriptRunner(script=object(), stdout=sentinal).stdout
        )


    def test_stderrDefault(self):
        """
        `FlockerScriptRunner.stderr` is `sys.stderr` by default.
        """
        self.assertIdentical(
            sys.stderr,
            FlockerScriptRunner(script=object()).stderr
        )


    def test_stderrOverride(self):
        """
        `FlockerScriptRunner.stderr` can be overridden in the constructor.
        """
        sentinal = object()
        self.assertIdentical(
            sentinal,
            FlockerScriptRunner(script=object(), stderr=sentinal).stderr
        )


    def test_parseOptions(self):
        """
        `FlockerScriptRunner._parseOptions` accepts a list of arguments,
        instantiates a `usage.Options` instance using the the `options` factory
        of the supplied script; passing stdout and stdin arguments to it.
        It then calls the `parseOptions` method with the supplied arguments and
        returns the populated options instance.
        """
        class FakeOptions(usage.Options):
            def __init__(self, stdout, stderr):
                usage.Options.__init__(self)
                self.stdout = stdout
                self.stderr = stderr

            def parseOptions(self, arguments):
                self.parseOptionsArguments = arguments

        class FakeScript(object):
            options = FakeOptions

        expectedArguments = [object(), object()]
        runner = FlockerScriptRunner(script=FakeScript, stdout=object(), stderr=object())
        options = runner._parseOptions(expectedArguments)
        self.assertEqual(
            (runner.stdout, runner.stderr, expectedArguments),
            (options.stdout, options.stderr, options.parseOptionsArguments)
        )


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
            def __init__(self, stdout, stderr):
                usage.Options.__init__(self)

            def parseOptions(self, arguments):
                raise usage.UsageError(expectedMessage)


        class FakeScript(object):
            options = FakeOptions

        stderr = io.BytesIO()

        runner = FlockerScriptRunner(script=FakeScript, stdout=object(), stderr=stderr)
        error = self.assertRaises(SystemExit, runner._parseOptions, [])
        expectedErrorMessage = b'ERROR: %s\n' % (expectedMessage,)
        errorText = stderr.getvalue()
        self.assertEqual(
            (1, [], expectedErrorMessage),
            (error.code, helpProblems('test_command', errorText), errorText[-len(expectedErrorMessage):])
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
        stderr = io.BytesIO()
        script = FlockerScriptRunner(self.script, stderr=stderr)
        error = self.assertRaises(
            SystemExit,
            script.main,
            b'--unexpected-argument'
        )
        error_text = stderr.getvalue()
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

    def test_version(self):
        """
        Flocker commands have a I{--version} option which prints the current
        version string to stdout and causes the command to exit with status 0.
        """
        stdout = io.BytesIO()
        error = self.assertRaises(
            SystemExit, self.options(stdout=stdout).parseOptions, ['--version'])
        self.assertEqual(
            (__version__ + '\n', 0),
            (stdout.getvalue(), error.code)
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
