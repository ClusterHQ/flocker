"""
Functional tests for ``flocker.common.script``.
"""

from __future__ import print_function

import os
import sys
from json import loads
from signal import SIGINT

from zope.interface import implementer

from eliot import Logger, Message
from eliot.testing import assertContainsFields

from twisted.trial.unittest import TestCase
from twisted.internet.utils import getProcessOutput
from twisted.internet.defer import succeed, Deferred
from twisted.python.log import msg, err
from twisted.python.filepath import FilePath

from ..script import ICommandLineScript


@implementer(ICommandLineScript)
class EliotScript(object):
    def main(self, reactor, options):
        logger = Logger()
        Message.new(key=123).write(logger)
        return succeed(None)


@implementer(ICommandLineScript)
class TwistedScript(object):
    def main(self, reactor, options):
        msg(b"hello")
        return succeed(None)


@implementer(ICommandLineScript)
class TwistedErrorScript(object):
    def main(self, reactor, options):
        err(ZeroDivisionError("onoes"), b"A zero division ono")
        return succeed(None)


@implementer(ICommandLineScript)
class StdoutStderrScript(object):
    def main(self, reactor, options):
        sys.stdout.write(b"stdout!\n")
        sys.stderr.write(b"stderr!\n")
        return succeed(None)


@implementer(ICommandLineScript)
class FailScript(object):
    def main(self, reactor, options):
        raise ZeroDivisionError("ono")


@implementer(ICommandLineScript)
class SigintScript(object):
    def main(self, reactor, options):
        reactor.callLater(0.05, os.kill, os.getpid(), SIGINT)
        return Deferred()


def read_eliot_logs(data):
    """
    Parse lines of eliot log output in to a list of message dictionaries.

    :param bytes data: Lines of eliot log output.

    :return: List of eliot message dictionaries.
    """
    return map(loads, data.splitlines())


def make_functional_logging_test(run_script):
    """
    Create tests for :class:`ILoggingPolicy` providers.

    :param run_script: Function that takes a test case, and a
        :class:`ICommandLineScript` implementer from this module,
        and returns the log output of running the script.
    """

    class FlockerScriptRunnerTests(TestCase):
        """
        Functional logging tests for ``FlockerScriptRunner``.
        """

        def test_eliot_messages(self):
            """
            Logged ``eliot`` messages get written to standard out.
            """
            d = run_script(self, EliotScript).addCallback(read_eliot_logs)
            d.addCallback(
                lambda messages: assertContainsFields(self, messages[1],
                                                      {u"key": 123}))
            return d

        def test_twisted_messages(self):
            """
            Logged Twisted messages get written to standard out as ``eliot``
            messages.
            """
            d = run_script(self, TwistedScript).addCallback(read_eliot_logs)
            d.addCallback(lambda messages: assertContainsFields(
                self, messages[1], {u"message_type": u"twisted:log",
                                    u"message": u"hello",
                                    u"error": False}))
            return d

        def test_twisted_errors(self):
            """
            Logged Twisted errors get written to standard out as ``eliot``
            messages.
            """
            message = (u'A zero division ono\n'
                       u'Traceback (most recent call last):\n'
                       u'Failure: exceptions.ZeroDivisionError: onoes\n')
            d = run_script(
                self, TwistedErrorScript).addCallback(read_eliot_logs)
            d.addCallback(lambda messages: assertContainsFields(
                self, messages[1], {u"message_type": u"twisted:log",
                                    u"message": message,
                                    u"error": True}))
            return d

        def test_error(self):
            """
            A script that raises an exception exits, logging the error as an
            ``eliot` message.
            """
            d = run_script(self, FailScript).addCallback(read_eliot_logs)

            def got_messages(messages):
                assertContainsFields(self, messages[1],
                                     {u"message_type": u"twisted:log",
                                      u"error": True})
                self.assertTrue(messages[1][u"message"].startswith(
                    u"Unhandled Error\nTraceback (most recent call last):\n"))
                self.assertTrue(messages[1][u"message"].endswith(
                    u"ZeroDivisionError: ono\n"))
            d.addCallback(got_messages)
            return d

        def test_sigint(self):
            """
            A script that is killed by signal exits, logging the signal.
            """
            d = run_script(self, SigintScript).addCallback(read_eliot_logs)
            d.addCallback(lambda messages: assertContainsFields(
                self, messages[1],
                {u"message_type": u"twisted:log",
                 u"message": u"Received SIGINT, shutting down.",
                 u"error": False}))
            return d

    return FlockerScriptRunnerTests


def log_script_output(output, script, source):
    """
    Log the output of a script for testing debugging.

    :param bytes output: The output of the script.
    :param ICommandLineScript script: The script being run.
    :param unicode source: The source of the output.

    :return bytes: The output of the script.
    """
    Message.new(
        message_type=u"flocker.common.functional.test_script:script_output",
        source=source,
        script=script.__name__,
        output=output).write()
    return output


def run_stdout_script(case, script):
    """
    Run a script that uses ``FlockerScriptRunner`` and ``StdoutLoggingPolicy``.

    :param ICommandLineScript: Script to run. Must be class in this module.

    :return: ``Deferred`` that fires with the output of the script.
    """
    code = b'''\
from twisted.python.usage import Options
from flocker.common.script import FlockerScriptRunner, StdoutLoggingPolicy

from flocker.common.functional.test_script import {}

FlockerScriptRunner({}(), Options, logging_policy=StdoutLoggingPolicy()).main()
'''.format(script.__name__, script.__name__)
    d = getProcessOutput(sys.executable, [b"-c", code], env=os.environ,
                         errortoo=True)

    d.addCallback(log_script_output, script=script, source=u"stdout")
    return d


class StdoutLoggingTests(make_functional_logging_test(run_stdout_script)):
    """
    Functional test for logging  for ``FlockerScriptRunner`` with
    ``StdoutLoggingPolicy``.
    """

    def test_stdout_stderr(self):
        """
        Output from Python code writing to ``sys.stdout`` and ``sys.stderr``
        is captured and turned into Eliot log messages.
        """
        d = run_stdout_script(
            self, StdoutStderrScript).addCallback(read_eliot_logs)

        def got_messages(messages):
            assertContainsFields(self, messages[1],
                                 {u"message_type": u"twisted:log",
                                  u"message": u"stdout!",
                                  u"error": False})
            assertContainsFields(self, messages[2],
                                 {u"message_type": u"twisted:log",
                                  u"message": u"stderr!",
                                  u"error": True})
        d.addCallback(got_messages)
        return d


def run_cli_script(case, script, capture_stdout=False):
    """
    Run a script that uses ``FlockerScriptRunner`` and ``CLILoggingPolicy``.

    :param ICommandLineScript: Script to run. Must be class in this module.
    :param bool capture_stdout: Whether to capture the standard output of the
        script, or the logfile generated by the script.

    :return: ``Deferred`` that fires with output the script or the contents
        of the generated logfile.
    """
    log_dir = FilePath(case.mktemp())
    log_dir.createDirectory()

    code = b'''\
from twisted.python.usage import Options
from flocker.common.script import FlockerScriptRunner, CLILoggingPolicy

from flocker.common.functional.test_script import {}

def getpid():
    return 1234

FlockerScriptRunner(
    {}(), Options,
    logging_policy=CLILoggingPolicy(_getpid=getpid)).main()
'''.format(script.__name__, script.__name__)
    d = getProcessOutput(
        sys.executable,
        [b"-c", code, '--log-dir', log_dir.path],
        env=os.environ,
        errortoo=True)

    d.addCallback(log_script_output, script=script, source=u"stdout")

    if not capture_stdout:
        d.addCallback(lambda _: log_dir.child('-c-1234.log').getContent())
        d.addCallback(log_script_output, script=script, source=u"logfile")
    return d


class CLILoggingTests(make_functional_logging_test(run_cli_script)):
    """
    Functional test for logging  for ``FlockerScriptRunner`` with
    ``CLILoggingPolicy``.
    """

    def test_stdout_stderr(self):
        """
        Output from Python code writing to ``sys.stdout`` and ``sys.stderr``
        is passed to standard output or error.
        """
        d = run_cli_script(self, StdoutStderrScript, capture_stdout=True)

        def got_output(output):
            # We use a set here since stdout and stderr aren't ordered
            # with respect to one another.
            self.assertEqual(
                set(output.splitlines()),
                {b"stdout!", b"stderr!"})
        d.addCallback(got_output)
        return d

    def test_stdout_stderr_logfile(self):
        """
        Output from Python code writing to ``sys.stdout`` and ``sys.stderr``
        is not captured.
        """
        d = run_cli_script(
            self, StdoutStderrScript).addCallback(read_eliot_logs)

        def got_messages(messages):
            twisted_messages = {
                message[u'message']
                for message in messages
                if message[u'message_type'] == u"twisted:log"}
            self.assertFalse(
                twisted_messages.intersection({u"stdout!", u"stderr!"}),
                "Standard output or error captured in log.")
        d.addCallback(got_messages)
        return d
