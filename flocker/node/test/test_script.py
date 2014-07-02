# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Tests for :module:`flocker.volume.script`."""

from twisted.trial.unittest import SynchronousTestCase
from ...testtools import FlockerScriptTestsMixin, StandardOptionsTestsMixin
from ..script import NodeOptions, NodeScript


class NodeScriptTests(FlockerScriptTestsMixin, SynchronousTestCase):
    """
    Tests for L{NodeScript}.
    """
    script = NodeScript
    options = NodeOptions
    command_name = u'flocker-node'


class NodeScriptMainTests(SynchronousTestCase):
    """
    Tests for ``NodeScript.main``.
    """

    def test_deferred_result(self):
        """
        ``NodeScript.main`` returns a ``Deferred`` on success.
        """
        script = NodeScript()
        options = NodeOptions()
        dummy_reactor = object()
        self.assertIs(
            None,
            self.successResultOf(script.main(dummy_reactor, options))
        )


class NodeOptionsTests(StandardOptionsTestsMixin, SynchronousTestCase):
    """Tests for :class:`FlockerVolumeOptions`."""
    options = NodeOptions

    def test_custom_configs(self):
        """
        If paths to configuration files are given then they are saved as
        ``FilePath`` instances on the options instance.
        """
        options = self.options()
        deploy = "foo"
        app = "bar"
        options.parseOptions([deploy, app])
        self.assertDictContainsSubset({'deployment_config': deploy,
                                       'app_config': app},
                                      options)
