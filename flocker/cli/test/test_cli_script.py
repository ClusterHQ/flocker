# Copyright ClusterHQ Inc.  See LICENSE file for details.

from twisted.trial.unittest import TestCase, SynchronousTestCase
from ...testtools import make_flocker_script_test, StandardOptionsTestsMixin
from ..script import CLIScript, CLIOptions


class FlockerCLITests(
        make_flocker_script_test(CLIScript, CLIOptions, u'flocker')
):
    """Tests for ``flocker`` CLI."""


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
