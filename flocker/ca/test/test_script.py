# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

from twisted.trial.unittest import TestCase, SynchronousTestCase
from ...testtools import FlockerScriptTestsMixin, StandardOptionsTestsMixin
from .._script import CAScript, CAOptions


class FlockerCATests(FlockerScriptTestsMixin, TestCase):
    """
    Tests for ``flocker-ca`` CLI.
    """
    script = CAScript
    options = CAOptions
    command_name = u'flocker-ca'


class CAOptionsTests(StandardOptionsTestsMixin, SynchronousTestCase):
    """
    Tests for :class:`CAOptions`.
    """
    options = CAOptions


class FlockerCAMainTests(TestCase):
    """
    Tests for ``CAScript.main``.
    """
    def test_deferred_result(self):
        """
        ``CAScript.main`` returns a ``Deferred`` on success.
        """
        options = CAOptions()
        options.parseOptions(["initialize", "mycluster"])

        script = CAScript()
        dummy_reactor = object()

        self.assertEqual(
            None,
            self.successResultOf(script.main(dummy_reactor, options))
        )
