# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

class ControlScriptTests(SynchronousTestCase):
    def test_starts_http_api_server(self):
        """
        ``ControlScript.main`` starts a HTTP server on the given port.
        """
        self.script.main(self.reactor, {"port": 8001}, self.service)
        server = self.reactor.tcpServers[0]
        port = server[0]
        factory = server[1].__class__
        self.assertEqual((port, factory), (8001, Site))
