# Copyright ClusterHQ Inc.  See LICENSE file for details.

from ...testtools import (
    FlockerScriptTestsMixin, StandardOptionsTestsMixin, TestCase,
)
from ..script import CLIScript, CLIOptions


class FlockerCLITests(FlockerScriptTestsMixin, TestCase):
    """Tests for ``flocker`` CLI."""
    script = CLIScript
    options = CLIOptions
    command_name = u'flocker'


class CLIOptionsTests(StandardOptionsTestsMixin, TestCase):
    """Tests for :class:`CLIOptions`."""

    # XXX: Actual tests live in StandardOptionsTestsMixin. FLOC-3794 says we
    # should make those tests use a pattern similar to
    # make_iblockdeviceapi_tests. tests
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
