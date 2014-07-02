# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Tests for :module:`flocker.volume.script`."""

import sys

from twisted.trial.unittest import SynchronousTestCase
from twisted.python.filepath import FilePath

from ...testtools import (
    FlockerScriptTestsMixin, StandardOptionsTestsMixin, FakeSysModule)
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
    # def test_create_configuration_error(self):
    #     """
    #     ``VolumeScript.main`` catches ``CreateConfigurationError``\ s raised by
    #     ``startService`` and writes an error message to stderr before exiting
    #     with code 1.
    #     """
    #     class RaisingService(object):
    #         def __init__(self, config_path, pool):
    #             pass
    #
    #         def startService(self):
    #             raise CreateConfigurationError('Foo')
    #
    #     fake_sys = FakeSysModule()
    #     script = VolumeScript(sys_module=fake_sys)
    #     script._service_factory = RaisingService
    #     dummy_reactor = object()
    #     options = VolumeOptions()
    #     options["config"] = FilePath(b'/foo/bar/baz')
    #     error = self.assertRaises(
    #         SystemExit, script.main, dummy_reactor, options)
    #
    #     self.assertEqual(
    #         (1, b'Writing config file /foo/bar/baz failed: Foo\n'),
    #         (error.code, fake_sys.stderr.getvalue())
    #     )

    def test_deferred_result(self):
        """
        ``VolumeScript.main`` returns a ``Deferred`` on success.
        """
        script = NodeScript()
        options = NodeOptions()
        options["config"] = FilePath(self.mktemp())
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
        self.assertDictContainsSubset({'deployment_config' : deploy,
                                       'app_config': app},
                                      options)
