# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.control._clusterstate``.
"""

from uuid import uuid4

from twisted.trial.unittest import SynchronousTestCase
from twisted.python.filepath import FilePath

from .._clusterstate import ClusterStateService
from .._model import (
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
    WITH_APPS = NodeState(hostname=u"host1", applications=[APP1, APP2])
    WITH_MANIFESTATION = NodeState(
        hostname=u"host2",
        manifestations={MANIFESTATION.dataset_id: MANIFESTATION}
    )

    def service(self):
        service = ClusterStateService()
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
            NodeState(hostname=u"host1", applications=[APP1]),
            NodeState(hostname=u"host1", applications=None,
                      manifestations={
                          MANIFESTATION.dataset_id:
                          MANIFESTATION})
        ])
        self.assertEqual(service.as_deployment(),
                         DeploymentState(nodes=[NodeState(
                             hostname=u"host1",
                             manifestations={
                                 MANIFESTATION.dataset_id: MANIFESTATION},
                             applications=[APP1])]))

    def test_update(self):
        """
        An update for previously given hostname overrides the previous state
        of that hostname.
        """
        service = self.service()
        service.apply_changes([
            NodeState(hostname=u"host1", applications=[APP1]),
            NodeState(hostname=u"host1", applications=[APP2]),
        ])
        self.assertEqual(service.as_deployment(),
                         DeploymentState(nodes=[NodeState(
                             hostname=u"host1",
                             applications=frozenset([APP2]))]))

    def test_multiple_hosts(self):
        """
        The information from multiple hosts is combined by
        ``ClusterStateService.as_deployment``.
        """
        service = self.service()
        service.apply_changes([
            NodeState(hostname=u"host1", applications=[APP1]),
            NodeState(hostname=u"host2", applications=[APP2]),
        ])
        self.assertEqual(service.as_deployment(),
                         DeploymentState(nodes=[
                             NodeState(
                                 hostname=u"host1",
                                 applications=frozenset([APP1])),
                             NodeState(
                                 hostname=u"host2",
                                 applications=frozenset([APP2])),
                         ]))

    def test_manifestation_path(self):
        """
        ``manifestation_path`` returns the path on the filesystem where the
        given dataset exists.
        """
        service = self.service()
        service.apply_changes([
            NodeState(hostname=u"host1",
                      manifestations={
                          MANIFESTATION.dataset_id:
                          MANIFESTATION},
                      paths={MANIFESTATION.dataset_id:
                             FilePath(b"/xxx/yyy")})
        ])
        self.assertEqual(
            service.manifestation_path(u"host1", MANIFESTATION.dataset_id),
            FilePath(b"/xxx/yyy"))
