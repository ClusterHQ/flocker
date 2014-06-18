# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Tests for :module:`flocker.volume.script`."""

import sys

from twisted.trial.unittest import SynchronousTestCase
from twisted.python.filepath import FilePath

from flocker.common.test.test_script import (
    FlockerScriptTestsMixin, StandardOptionsTestsMixin, FakeSysModule)
from flocker.volume.script import VolumeOptions, VolumeScript
from flocker.volume.service import VolumeService, CreateConfigurationError


class VolumeScriptTests(FlockerScriptTestsMixin, SynchronousTestCase):
    """
    Tests for L{VolumeScript}.
    """
    script = VolumeScript
    options = VolumeOptions
    command_name = 'flocker-volume'


class VolumeScriptInitTests(SynchronousTestCase):
    """
    Tests for ``VolumeScript.__init__``.
    """
    def test_sys_module_default(self):
        """
        ``VolumeScript._sys_module`` is ``sys`` by default.
        """
        self.assertIs(sys, VolumeScript()._sys_module)

    def test_sys_module_override(self):
        """
        ``VolumeScript._sys_module`` can be overridden in the constructor.
        """
        dummy_sys = object()
        self.assertIs(dummy_sys,
                      VolumeScript(sys_module=dummy_sys)._sys_module)

    def test_service_factory_default(self):
        """
        ``VolumeScript._service_factory`` is ``VolumeService`` by default.
        """
        self.assertIs(VolumeService, VolumeScript._service_factory)


class VolumeScriptMainTests(SynchronousTestCase):
    """
    Tests for ``VolumeScript.main``.
    """
    def test_createConfigurationError(self):
        """
        ``VolumeScript.main`` catches ``CreateConfigurationError`` s raised by
        ``startService`` and writes an error message to stderr before exiting
        with code 1.
        """
        class RaisingService(object):
            def __init__(self, config_path, pool):
                pass

            def startService(self):
                raise CreateConfigurationError('Foo')

        fake_sys = FakeSysModule()
        script = VolumeScript(sys_module=fake_sys)
        script._service_factory = RaisingService
        dummy_reactor = object()
        options = dict(config=FilePath(b'/foo/bar/baz'))
        error = self.assertRaises(
            SystemExit, script.main, dummy_reactor, options)

        self.assertEqual(
            (1, b'Writing config file /foo/bar/baz failed: Foo\n'),
            (error.code, fake_sys.stderr.getvalue())
        )

    def test_deferred_result(self):
        """
        ``VolumeScript.main`` returns a ``Deferred`` on success.
        """
        script = VolumeScript()
        options = dict(config=FilePath(self.mktemp()))
        dummy_reactor = object()
        self.assertIs(
            None,
            self.successResultOf(script.main(dummy_reactor, options))
        )


class VolumeOptionsTests(StandardOptionsTestsMixin, SynchronousTestCase):
    """Tests for :class:`FlockerVolumeOptions`."""
    options = VolumeOptions

    def test_default_config(self):
        """By default the config file is ``b'/etc/flocker/volume.json'``."""
        options = self.options()
        options.parseOptions([])
        self.assertEqual(options["config"],
                         FilePath(b"/etc/flocker/volume.json"))

    def test_custom_config(self):
        """A custom config file can be specified with ``--config``."""
        options = self.options()
        options.parseOptions([b"--config", b"/path/somefile.json"])
        self.assertEqual(options["config"],
                         FilePath(b"/path/somefile.json"))
