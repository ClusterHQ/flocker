# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.control._clusterstate``.
"""

from uuid import uuid4

from twisted.trial.unittest import SynchronousTestCase
from twisted.python.filepath import FilePath
from twisted.internet.task import Clock

from .._clusterstate import EXPIRATION_TIME, ClusterStateService
from .. import (
    Application, DockerImage, NodeState, DeploymentState, Manifestation,
    Dataset,
)

APP1 = Application(
    name=u"webserver", image=DockerImage.from_string(u"apache"))
APP2 = Application(
    name=u"database", image=DockerImage.from_string(u"postgresql"))
MANIFESTATION = Manifestation(dataset=Dataset(dataset_id=unicode(uuid4())),
                              primary=True)


class ClusterStateServiceTests(SynchronousTestCase):
    """
    Tests for ``ClusterStateService``.
    """
    WITH_APPS = NodeState(hostname=u"host1", applications=[APP1, APP2],
                          used_ports=[])
    WITH_MANIFESTATION = NodeState(
        hostname=u"host2",
        manifestations={MANIFESTATION.dataset_id: MANIFESTATION},
        devices={}, paths={},
    )

    def setUp(self):
        self.clock = Clock()

    def service(self):
        service = ClusterStateService(self.clock)
        service.startService()
        self.addCleanup(service.stopService)
        return service

    def test_applications(self):
        """
        ``ClusterStateService.as_deployment`` copies applications from the
        given node state.
        """
        service = self.service()
        service.apply_changes([self.WITH_APPS])
        self.assertEqual(
            service.as_deployment(),
            DeploymentState(nodes=[self.WITH_APPS])
        )

    def test_other_manifestations(self):
        """
        ``ClusterStateService.as_deployment`` copies over other manifestations
        to the ``Node`` instances it creates.
        """
        service = self.service()
        service.apply_changes([self.WITH_MANIFESTATION])
        self.assertEqual(
            service.as_deployment(),
            DeploymentState(nodes={self.WITH_MANIFESTATION})
        )

    def test_partial_update(self):
        """
        An update that is ignorant about certain parts of a node's state only
        updates the information it knows about.
        """
        service = self.service()
        service.apply_changes([
            NodeState(hostname=u"host1", applications=[APP1], used_ports=[]),
            NodeState(hostname=u"host1", applications=None,
                      manifestations={
                          MANIFESTATION.dataset_id:
                          MANIFESTATION},
                      devices={}, paths={})
        ])
        self.assertEqual(service.as_deployment(),
                         DeploymentState(nodes=[NodeState(
                             hostname=u"host1",
                             manifestations={
                                 MANIFESTATION.dataset_id: MANIFESTATION},
                             devices={}, paths={},
                             used_ports=[],
                             applications=[APP1])]))

    def test_update(self):
        """
        An update for previously given hostname overrides the previous state
        of that hostname.
        """
        service = self.service()
        service.apply_changes([
            NodeState(hostname=u"host1", applications=[APP1], used_ports=[]),
            NodeState(hostname=u"host1", applications=[APP2], used_ports=[]),
        ])
        self.assertEqual(service.as_deployment(),
                         DeploymentState(nodes=[NodeState(
                             hostname=u"host1",
                             used_ports=[],
                             applications=frozenset([APP2]))]))

    def test_multiple_hosts(self):
        """
        The information from multiple hosts is combined by
        ``ClusterStateService.as_deployment``.
        """
        service = self.service()
        service.apply_changes([
            NodeState(hostname=u"host1", applications=[APP1], used_ports=[]),
            NodeState(hostname=u"host2", applications=[APP2], used_ports=[]),
        ])
        self.assertEqual(service.as_deployment(),
                         DeploymentState(nodes=[
                             NodeState(
                                 hostname=u"host1",
                                 used_ports=[],
                                 applications=frozenset([APP1])),
                             NodeState(
                                 hostname=u"host2",
                                 used_ports=[],
                                 applications=frozenset([APP2])),
                         ]))

    def test_manifestation_path(self):
        """
        ``manifestation_path`` returns the path on the filesystem where the
        given dataset exists.
        """
        identifier = uuid4()
        service = self.service()
        service.apply_changes([
            NodeState(hostname=u"host1", uuid=identifier,
                      manifestations={
                          MANIFESTATION.dataset_id:
                          MANIFESTATION},
                      paths={MANIFESTATION.dataset_id:
                             FilePath(b"/xxx/yyy")},
                      devices={})
        ])
        self.assertEqual(
            service.manifestation_path(identifier, MANIFESTATION.dataset_id),
            FilePath(b"/xxx/yyy"))

    def test_expiration(self):
        """
        Information updates that are more than the hard-coded expiration period
        (in seconds) old are wiped.
        """
        service = self.service()
        app_node = NodeState(hostname=u"10.0.0.1", uuid=uuid4(),
                             manifestations=None, devices=None, paths=None,
                             applications=[APP1], used_ports=[])
        service.apply_changes([app_node])
        self.clock.advance(EXPIRATION_TIME - 1)
        before_wipe_state = service.as_deployment()
        self.clock.advance(1)
        after_wipe_state = service.as_deployment()
        self.assertEqual(
            [before_wipe_state, after_wipe_state],
            [DeploymentState(nodes=[app_node]), DeploymentState()])

    def test_updates_different_key(self):
        """
        A wipe created by a ``IClusterStateChange`` with a given wipe key is
        not overwritten by a later ``IClusterStateChange`` with a different
        key.
        """
        service = self.service()
        app_node = NodeState(hostname=u"10.0.0.1", uuid=uuid4(),
                             manifestations=None, devices=None, paths=None,
                             applications=[APP1], used_ports=[])
        app_node_2 = NodeState(hostname=app_node.hostname, uuid=app_node.uuid,
                               manifestations={
                                   MANIFESTATION.dataset_id: MANIFESTATION},
                               devices={}, paths={})
        service.apply_changes([app_node])
        self.clock.advance(1)
        service.apply_changes([app_node_2])
        self.clock.advance(EXPIRATION_TIME - 1)
        before_wipe_state = service.as_deployment()
        self.clock.advance(1)
        after_wipe_state = service.as_deployment()
        self.assertEqual(
            [before_wipe_state, after_wipe_state],
            [DeploymentState(nodes=[app_node_2]), DeploymentState()])

    def test_update_with_same_key(self):
        """
        An update with the same key as a previous one delays wiping.
        """
        service = self.service()
        app_node = NodeState(hostname=u"10.0.0.1", uuid=uuid4(),
                             manifestations=None, devices=None, paths=None,
                             applications=[APP1], used_ports=[])
        service.apply_changes([app_node])
        self.clock.advance(1)
        service.apply_changes([app_node])
        self.clock.advance(9)
        self.assertEqual(service.as_deployment(),
                         DeploymentState(nodes=[app_node]))
