"""
Functional tests for ``flocker.common.script``.
"""

import os
import sys
from json import loads

from zope.interface import implementer

from eliot import Logger, Message
from eliot.testing import assertContainsFields

from twisted.trial.unittest import TestCase
from twisted.internet.utils import getProcessOutput
from twisted.internet.defer import succeed
from twisted.python.log import msg

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
        d = getProcessOutput(sys.executable, [b"-c", code], env=os.environ)
        d.addCallback(lambda data: map(loads, data.splitlines()))
        return d

    def test_eliot_messages(self):
        """
        Logged ``eliot`` messages get written to standard out.
        """
        d = self.run_script(EliotScript)
        d.addCallback(lambda messages: assertContainsFields(self, messages[0],
                                                            {u"key": 123}))
        return d

    def test_twisted_messages(self):
        """
        Logged Twisted messages get written to standard out as ``eliot``
        messages.
        """
        d = self.run_script(TwistedScript)
        d.addCallback(lambda messages: assertContainsFields(
            self, messages[0], {u"message_type": u"eliot:twisted",
                                u"message": u"hello",
                                u"error": False}))
        return d
