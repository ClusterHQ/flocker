# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

from twisted.trial.unittest import SynchronousTestCase
from twisted.python.filepath import FilePath

from ..script import ControlOptions, ControlScript
from ...testtools import MemoryCoreReactor, StandardOptionsTestsMixin
from .._clusterstate import ClusterStateService
from ..httpapi import REST_API_PORT

from ...ca.testtools import get_credential_sets


class ControlOptionsTests(StandardOptionsTestsMixin,
                          SynchronousTestCase):
    """
    Tests for ``ControlOptions``.
    """
    options = ControlOptions

    def test_default_port(self):
        """
        The default REST API port configured by ``ControlOptions`` is the
        appropriate shared constant.
        """
        options = ControlOptions()
        options.parseOptions([])
        self.assertEqual(options["port"], b'tcp:%d' % (REST_API_PORT,))

    def test_custom_port(self):
        """
        The ``--port`` command-line option allows configuring the REST API
        port.
        """
        options = ControlOptions()
        options.parseOptions([b"--port", b"tcp:1234"])
        self.assertEqual(options["port"], b"tcp:1234")

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

    def test_default_agent_port(self):
        """
        The default AMP port configured by ``ControlOptions`` is 4524.
        """
        options = ControlOptions()
        options.parseOptions([])
        self.assertEqual(options["agent-port"], b'tcp:4524')

    def test_custom_agent_port(self):
        """
        The ``--port`` command-line option allows configuring the REST API
        port.
        """
        options = ControlOptions()
        options.parseOptions([b"--agent-port", b"tcp:1234"])
        self.assertEqual(options["agent-port"], b"tcp:1234")


class ControlScriptTests(SynchronousTestCase):
    """
    Tests for ``ControlScript``.
    """
    def setUp(self):
        """
        Create some certificates to use when creating the control service.
        """
        ca_set, _ = get_credential_sets()
        self.certificate_path = FilePath(self.mktemp())
        self.certificate_path.makedirs()
        ca_set.copy_to(self.certificate_path, control=True)
        self.script = ControlScript()
        self.options = ControlOptions()
        self.data_path = FilePath(self.mktemp())
        self.options.parseOptions([
            b"--port", b"tcp:8001", b"--agent-port", b"tcp:8002",
            b"--data-path", self.data_path.path,
            b"--certificates-directory", self.certificate_path.path
        ])

    def test_no_immediate_stop(self):
        """
        The ``Deferred`` returned from ``ControlScript`` is not fired.
        """
        self.assertNoResult(
            self.script.main(MemoryCoreReactor(), self.options))

    def test_starts_persistence_service(self):
        """
        ``ControlScript.main`` starts a configuration persistence service.
        """
        reactor = MemoryCoreReactor()
        self.script.main(reactor, self.options)
        self.assertTrue(self.data_path.isdir())

    def test_starts_cluster_state_service(self):
        """
        ``ControlScript.main`` starts a cluster state service.
        """
        reactor = MemoryCoreReactor()
        self.script.main(reactor, self.options)
        server = reactor.tcpServers[0]
        control_resource = server[1].wrappedFactory.resource
        service = control_resource._v1_user.cluster_state_service
        self.assertEqual((service.__class__, service.running),
                         (ClusterStateService, True))
