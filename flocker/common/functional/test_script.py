"""
Functional tests for ``flocker.common.script``.
"""

from twisted.trial.unittest import TestCase
from twisted.internet.utils import getProcessOutput

from ..script import FlockerScriptRunner


class FlockerScriptRunnerTests(TestCase):
    """
    Functional tests for ``FlockerScriptRunner``.
    """
    def test_eliot_messages(self):
        """
        Logged ``eliot`` messages get written to standard out.
        """

    def test_twisted_messages(self):
        """
        Logged Twisted messages get written to standard out as ``eliot``
        messages.
        """

    def test_twisted_errors(self):
        """
        Logged Twisted errors get written to standard out as ``eliot``
        messages.
        """

    def test_non_blocking(self):
        """
        If standard out buffer fills up, the script is not blocked by logging.
        """
