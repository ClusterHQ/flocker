# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

from twisted.trial.unittest import TestCase, SynchronousTestCase
from ...testtools import FlockerScriptTestsMixin, StandardOptionsTestsMixin
from ..script import ProvisionScript, ProvisionOptions


class FlockerProvisionTests(FlockerScriptTestsMixin, TestCase):
    """Tests for ``flocker-provision`` CLI."""
    script = ProvisionScript
    options = ProvisionOptions
    command_name = u'flocker-provision'


class FlockerProvisionOptionsTests(
        StandardOptionsTestsMixin, SynchronousTestCase):
    """Tests for :class:`ProvisionOptions`."""
    options = ProvisionOptions


class FlockerCLIMainTests(TestCase):
    """ProvisionScript.main``.
    """
    def test_deferred_result(self):
        """
        ``ProvisionScript.main`` returns a ``Deferred`` on success.
        """
        options = ProvisionOptions()
        options.parseOptions([])

        script = ProvisionScript()
        dummy_reactor = object()

        self.assertEqual(
            None,
            self.successResultOf(script.main(dummy_reactor, options))
        )
