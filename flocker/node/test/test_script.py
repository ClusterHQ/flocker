# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Tests for :module:`flocker.volume.script`."""

from twisted.trial.unittest import SynchronousTestCase
from twisted.python.usage import UsageError
from yaml import safe_dump
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
        expected_deployment = {"foo":"bar", "spam":"eggs", "anumber":14}
        expected_application = {"appfoo":"appbar", "appspam":"appeggs", "appnumber":17}
        options.parseOptions([safe_dump(expected_deployment), safe_dump(expected_application)])
        self.assertDictContainsSubset({'deployment_config': expected_deployment,
                                       'app_config': expected_application},
                                      options)

    def test_invalid_configs(self):
        """
        If the deployment and appplication options passed are not valid YAML,
        a UsageError is raised.
        """
        options = self.options()
        deploymentBadYaml = "{'foo':'bar', 'x':y, '':'"
        applicationBadYaml = "{'abc':'def',,"
        e = self.assertRaises(UsageError,
                              options.parseOptions,
                              [deploymentBadYaml, applicationBadYaml])
        self.assertEqual(str(e), 'Deployment config could not be parsed as YAML')
