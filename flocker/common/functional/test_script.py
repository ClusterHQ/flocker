"""
Functional tests for ``flocker.common.script``.
"""

from __future__ import print_function

import os
import sys
from json import loads
from signal import SIGINT

from bitmath import MiB

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


class FlockerScriptRunnerTests(TestCase):
    """
    Functional tests for ``FlockerScriptRunner``.
    """
    def run_script(self, script, options=None):
        """
        Run a script that logs messages and uses ``FlockerScriptRunner``.

        :param ICommandLineScript: Script to run. Must be class in this module.
        :param list options: Extra command line options to pass to the
            script.

        :return: ``Deferred`` that fires with list of decoded JSON messages.
        """
        if options is None:
            options = []
        code = b'''\
from twisted.python.usage import Options
from flocker.common.script import FlockerScriptRunner, flocker_standard_options

from flocker.common.functional.test_script import {}

@flocker_standard_options
class StandardOptions(Options):
    pass

FlockerScriptRunner({}(), StandardOptions()).main()
'''.format(script.__name__, script.__name__)
        d = getProcessOutput(
            sys.executable, [b"-c", code] + options,
            env=os.environ,
            errortoo=True
        )
        d.addCallback(lambda data: map(loads, data.splitlines()))
        return d

    def test_eliot_messages(self):
        """
        Logged ``eliot`` messages get written to standard out.
        """
        d = self.run_script(EliotScript)
        d.addCallback(lambda messages: assertContainsFields(self, messages[1],
                                                            {u"key": 123}))
        return d

    def test_twisted_messages(self):
        """
        Logged Twisted messages get written to standard out as ``eliot``
        messages.
        """
        d = self.run_script(TwistedScript)
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
        message = (u'A zero division ono\nTraceback (most recent call '
                   u'last):\nFailure: exceptions.ZeroDivisionError: onoes\n')
        d = self.run_script(TwistedErrorScript)
        d.addCallback(lambda messages: assertContainsFields(
            self, messages[1], {u"message_type": u"twisted:log",
                                u"message": message,
                                u"error": True}))
        return d

    def test_stdout_stderr(self):
        """
        Output from Python code writing to ``sys.stdout`` and ``sys.stderr``
        is captured and turned into Eliot log messages.
        """
        d = self.run_script(StdoutStderrScript)

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

    def test_error(self):
        """
        A script that raises an exception exits, logging the error as an
        ``eliot` message.
        """
        d = self.run_script(FailScript)

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
        d = self.run_script(SigintScript)
        d.addCallback(lambda messages: assertContainsFields(
            self, messages[1], {u"message_type": u"twisted:log",
                                u"message": u"Received SIGINT, shutting down.",
                                u"error": False}))
        return d

    def _assert_logfile_messages(self, stdout_messages, logfile):
        """
        Verify that the messages have been logged to a file rather than to
        stdout.
        """
        self.assertEqual([], stdout_messages)
        logfile_messages = map(loads, logfile.getContent().splitlines())
        assertContainsFields(
            # message[0] contains a twisted log message.
            self, logfile_messages[1], {u"key": 123}
        )

    def test_file_logging(self):
        """
        Logged messages are written to ``logfile`` if ``--logfile`` is supplied
        on the command line.
        """
        logfile = FilePath(self.mktemp()).child('foo.log')
        logfile.parent().makedirs()
        d = self.run_script(EliotScript, options=['--logfile', logfile.path])
        d.addCallback(self._assert_logfile_messages, logfile=logfile)
        return d

    def test_file_logging_makedirs(self):
        """
        The parent directory is created if it doesn't already exist.
        """
        logfile = FilePath(self.mktemp()).child('foo.log')
        d = self.run_script(EliotScript, options=['--logfile', logfile.path])
        d.addCallback(self._assert_logfile_messages, logfile=logfile)
        return d

    def test_file_logging_rotation_at_100MiB(self):
        """
        Logfiles are rotated when they reach 100MiB.
        """
        logfile = FilePath(self.mktemp()).child('foo.log')
        logfile.parent().makedirs()
        with logfile.open('w') as f:
            f.truncate(int(MiB(100).to_Byte().value - 1))

        d = self.run_script(EliotScript, options=['--logfile', logfile.path])

        def verify_logfiles(stdout_messages, logfile):
            self.assertEqual(
                set([logfile, logfile.sibling(logfile.basename() + u'.1')]),
                set(logfile.parent().children())
            )
        d.addCallback(verify_logfiles, logfile=logfile)

        return d

    def test_file_logging_rotation_5_files(self):
        """
        Only 5 logfiles are kept.
        """
        logfile = FilePath(self.mktemp()).child('foo.log')
        logfile.parent().makedirs()
        # This file will become foo.log.1
        with logfile.open('w') as f:
            f.write(b'0')
            f.truncate(int(MiB(100).to_Byte().value))
        # These file extensions will be incremented
        for i in range(1, 5):
            sibling = logfile.sibling(logfile.basename() + u'.' + unicode(i))
            with sibling.open('w') as f:
                f.write(bytes(i))

        d = self.run_script(EliotScript, options=['--logfile', logfile.path])

        def verify_logfiles(stdout_messages, logfile):
            logfile_dir = logfile.parent()
            self.assertEqual(
                # The contents of the files will now be an integer one less
                # than the integer in the file name.
                map(bytes, range(0, 4)),
                list(
                    logfile_dir.child('foo.log.{}'.format(i)).open().read(1)
                    for i
                    in range(1, 5)
                )
            )
        d.addCallback(verify_logfiles, logfile=logfile)

        return d
