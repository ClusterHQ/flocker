# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for communication to applications.
"""
from subprocess import check_output
from yaml import safe_dump

from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase

from flocker.node._docker import Unit

from .utils import running_units, require_installed, get_nodes


class PortsTests(TestCase):
    """
    Tests for communication to applications.

    Similar to http://doc-dev.clusterhq.com/gettingstarted/tutorial/
    exposing-ports.html
    """
    def test_deployment_with_ports(self):
        """
        Ports specified are shown by docker inspect.
        """
        node_1, node_2 = get_nodes(num_nodes=2)

        temp = FilePath(self.mktemp())
        temp.makedirs()

        application_config = temp.child(b"application.yml")
        application_config.setContent(safe_dump({
            u"version": 1,
            u"applications": {
                u"mongodb-port-example": {
                    u"image": u"clusterhq/mongodb",
                    u"ports": [{
                        u"internal": 27017,
                        u"external": 27018,
                    }],
                },
            },
        }))

        deployment_config = temp.child(b"deployment.yml")
        deployment_config.setContent(safe_dump({
            u"version": 1,
            u"nodes": {
                node_1: [u"mongodb-port-example"],
                node_2: [],
            },
        }))

        check_output([b"flocker-deploy"] +
                     [deployment_config.path] +
                     [application_config.path])

        running = {
            node_1: running_units(node_1),
            node_2: running_units(node_2),
        }

        expected = set([
            Unit(name=u'/mongodb-port-example-data',
            container_name=u'/mongodb-port-example-data',
            activation_state=u'inactive',
            container_image=u'clusterhq/mongodb:latest',
            ports=frozenset(),
            environment=None, volumes=())
        ])

        self.assertEqual(
            running,
            {
                node_1: expected,
                node_2: set(),
            }
        )


    def atest_traffic_routed(self):
        """
        An application can be accessed even from a connection to a node
        which it is not running on.
        """
        pass
