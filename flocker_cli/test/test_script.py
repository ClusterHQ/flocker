# -*- coding: utf-8 -*-
# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

from twisted.trial.unittest import TestCase, SynchronousTestCase
from ..testtools import FlockerScriptTestsMixin, StandardOptionsTestsMixin
from ..script import CLIScript, CLIOptions


class FlockerCLITests(FlockerScriptTestsMixin, TestCase):
    """Tests for ``flocker`` CLI."""
    script = CLIScript
    options = CLIOptions
    command_name = u'flocker'


class CLIOptionsTests(StandardOptionsTestsMixin, SynchronousTestCase):
    """Tests for :class:`CLIOptions`."""
    options = CLIOptions


class FlockerCLIMainTests(TestCase):
    """
    Tests for ``CLIScript.main``.
    """
    def test_deferred_result(self):
        """
        ``CLIScript.main`` returns a ``Deferred`` on success.
        """
        options = CLIOptions()
        options.parseOptions([])

        script = CLIScript()
        dummy_reactor = object()

        self.assertEqual(
            None,
            self.successResultOf(script.main(dummy_reactor, options))
        )
