# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.control._protocol``.
"""

from uuid import uuid4

from twisted.trial.unittest import SynchronousTestCase

from .._protocol import NodeStateArgument, DeploymentArgument
from .._model import (
    Deployment, Application, DockerImage, Node, NodeState, Manifestation,
    Dataset,
)


APP1 = Application(
    name=u'myapp',
    image=DockerImage.from_string(u'postgresql'))
APP2 = Application(
    name=u'myapp2',
    image=DockerImage.from_string(u'mysql'))
TEST_DEPLOYMENT = Deployment(nodes=frozenset([
    Node(hostname=u'node1.example.com',
         applications=frozenset([APP1, APP2]))]))
MANIFESTATION = Manifestation(dataset=Dataset(dataset_id=unicode(uuid4())),
                              primary=True)


class SerializationTests(SynchronousTestCase):
    """
    Tests for argument serialization.
    """
    def test_nodestate(self):
        """
        ``NodeStateArgument`` can round-trip a ``NodeState`` instance.
        """
        argument = NodeStateArgument()
        node_state = NodeState(running=[APP1], not_running=[APP2],
                               used_ports=[1, 2],
                               other_manifestations=frozenset([MANIFESTATION]))
        as_bytes = argument.toString(node_state)
        deserialized = argument.fromString(as_bytes)
        self.assertEqual([bytes, node_state], [type(as_bytes), deserialized])

    def test_deployment(self):
        """
        ``DeploymentArgument`` can round-trip a ``Deployment`` instance.
        """
        argument = DeploymentArgument()
        as_bytes = argument.toString(TEST_DEPLOYMENT)
        deserialized = argument.fromString(as_bytes)
        self.assertEqual([bytes, TEST_DEPLOYMENT],
                         [type(as_bytes), deserialized])
