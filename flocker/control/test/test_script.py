# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

from twisted.web.server import Site
from twisted.trial.unittest import SynchronousTestCase
from twisted.python.filepath import FilePath

from ..script import ControlOptions, ControlScript
from ...testtools import MemoryCoreReactor, StandardOptionsTestsMixin


class ControlOptionsTests(StandardOptionsTestsMixin,
                          SynchronousTestCase):
    """
    Tests for ``ControlOptions``.
    """
    options = ControlOptions

    def test_default_port(self):
        """
        The default port configured by ``ControlOptions`` is 4523.
        """
        options = ControlOptions()
        options.parseOptions([])
        self.assertEqual(options["port"], 4523)

    def test_custom_port(self):
        """
        The ``--port`` command-line option allows configuring the port.
        """
        options = ControlOptions()
        options.parseOptions([b"--port", b"1234"])
        self.assertEqual(options["port"], 1234)

    def test_default_path(self):
        """
        The default data path configured by ``ControlOptions`` is
        ``b"/var/lib/flocker"``.
        """
        options = ControlOptions()
        options.parseOptions([])
        self.assertEqual(options["data-path"], FilePath(b"/var/lib/flocker"))

    def test_path(self):
        """
        The ``--data-path`` command-line option is converted to ``FilePath``.
        """
        options = ControlOptions()
        options.parseOptions([b"--data-path", b"/var/xxx"])
        self.assertEqual(options["data-path"], FilePath(b"/var/xxx"))


class ControlScriptEffectsTests(SynchronousTestCase):
    """
    Tests for effects ``ControlScript``.
    """
    def test_starts_http_api_server(self):
        """
        ``ControlScript.main`` starts a HTTP server on the given port.
        """
        options = ControlOptions()
        options.parseOptions(
            [b"--port", b"8001", b"--data-path", self.mktemp()])
        reactor = MemoryCoreReactor()
        ControlScript().main(reactor, options)
        server = reactor.tcpServers[0]
        port = server[0]
        factory = server[1].__class__
        self.assertEqual((port, factory), (8001, Site))

    def test_no_immediate_stop(self):
        """
        The ``Deferred`` returned from ``ControlScript`` is not fired.
        """
        script = ControlScript()
        options = ControlOptions()
        options.parseOptions([b"--data-path", self.mktemp()])
        self.assertNoResult(script.main(MemoryCoreReactor(), options))

    def test_starts_persistence_service(self):
        """
        ``ControlScript.main`` starts a configuration persistence service.
        """
        path = FilePath(self.mktemp())
        options = ControlOptions()
        options.parseOptions([b"--data-path", path.path])
        reactor = MemoryCoreReactor()
        ControlScript().main(reactor, options)
        self.assertTrue(path.isdir())
