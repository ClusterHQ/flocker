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


class VolumeScriptMainTests(SynchronousTestCase):
    """
    Tests for ``VolumeScript.main``.
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

    # def test_default_config(self):
    #     """By default the config file is ``b'/etc/flocker/volume.json'``."""
    #     options = self.options()
    #     options.parseOptions([])
    #     self.assertEqual(options["config"],
    #                      FilePath(b"/etc/flocker/volume.json"))
    #
    # def test_custom_config(self):
    #     """A custom config file can be specified with ``--config``."""
    #     options = self.options()
    #     options.parseOptions([b"--config", b"/path/somefile.json"])
    #     self.assertEqual(options["config"],
    #                      FilePath(b"/path/somefile.json"))
