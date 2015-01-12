# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

from twisted.web.server import Site
from twisted.trial.unittest import SynchronousTestCase

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
        options.parseOptions(["--port", 1234])
        self.assertEqual(options["port"], 1234)


class ControlScriptEffectsTests(SynchronousTestCase):
    """
    Tests for effects ``ControlScript``.
    """
    def test_starts_http_api_server(self):
        """
        ``ControlScript.main`` starts a HTTP server on the given port.
        """
        reactor = MemoryCoreReactor()
        ControlScript().main(reactor, {"port": 8001})
        server = reactor.tcpServers[0]
        port = server[0]
        factory = server[1].__class__
        self.assertEqual((port, factory), (8001, Site))

    def test_no_immediate_stop(self):
        """
        The ``Deferred`` returned from ``ControlScript`` is not fired.
        """
        script = ControlScript()
        self.assertNoResult(script.main(MemoryCoreReactor(), ControlOptions()))
