# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.control._clusterstate``.
"""

from uuid import uuid4

from twisted.trial.unittest import SynchronousTestCase

from .._clusterstate import ClusterStateService
from .._model import (
    Application, DockerImage, NodeState, Node, Deployment, Manifestation,
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
    def service(self):
        service = ClusterStateService()
        service.startService()
        self.addCleanup(service.stopService)
        return service

    def test_running_and_not_running_applications(self):
        """
        ``ClusterStateService.as_deployment`` combines both running and not
        running applications from the given node state.
        """
        service = self.service()
        service.update_node_state(NodeState(hostname=u"host1",
                                            running=[APP1],
                                            not_running=[APP2]))
        self.assertEqual(service.as_deployment(),
                         Deployment(nodes=frozenset([Node(
                             hostname=u"host1",
                             applications=frozenset([APP1, APP2]))])))

    def test_other_manifestations(self):
        """
        ``ClusterStateService.as_deployment`` copies over other manifestations
        to the ``Node`` instances it creates.
        """
        service = self.service()
        service.update_node_state(
            NodeState(hostname=u"host2", running=[], not_running=[],
                      manifestations=frozenset([MANIFESTATION])))
        self.assertEqual(service.as_deployment(),
                         Deployment(nodes=frozenset([Node(
                             hostname=u"host2",
                             applications=frozenset(),
                             manifestations={
                                 MANIFESTATION.dataset_id: MANIFESTATION},
                         )])))

    def test_update(self):
        """
        An update for previously given hostname overrides the previous state
        of that hostname.
        """
        service = self.service()
        service.update_node_state(NodeState(hostname=u"host1",
                                            running=[APP1], not_running=[]))
        service.update_node_state(NodeState(hostname=u"host1",
                                            running=[APP2], not_running=[]))
        self.assertEqual(service.as_deployment(),
                         Deployment(nodes=frozenset([Node(
                             hostname=u"host1",
                             applications=frozenset([APP2]))])))

    def test_multiple_hosts(self):
        """
        The information from multiple hosts is combined by
        ``ClusterStateService.as_deployment``.
        """
        service = self.service()
        service.update_node_state(NodeState(hostname=u"host1",
                                            running=[APP1], not_running=[]))
        service.update_node_state(NodeState(hostname=u"host2",
                                            running=[APP2], not_running=[]))
        self.assertEqual(service.as_deployment(),
                         Deployment(nodes=frozenset([
                             Node(
                                 hostname=u"host1",
                                 applications=frozenset([APP1])),
                             Node(
                                 hostname=u"host2",
                                 applications=frozenset([APP2])),
                         ])))
