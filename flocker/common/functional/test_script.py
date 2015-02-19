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
    def run_script(self, script):
        """
        Run a script that logs messages and uses ``FlockerScriptRunner``.

        :param ICommandLineScript: Script to run. Must be class in this module.

        :return: ``Deferred`` that fires with list of decoded JSON messages.
        """
        code = b'''\
from twisted.python.usage import Options
from flocker.common.script import FlockerScriptRunner

from flocker.common.functional.test_script import {}

FlockerScriptRunner({}(), Options()).main()
'''.format(script.__name__, script.__name__)
        d = getProcessOutput(sys.executable, [b"-c", code], env=os.environ,
                             errortoo=True)
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
