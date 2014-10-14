# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for deploying applications.

Run with:

  $ sudo -E PATH=$PATH $(type -p trial) --temp=/tmp/trial flocker.acceptance

if using Docker-in-Docker, else trial flocker.acceptance is fine
"""
from subprocess import check_output
from yaml import safe_dump

from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase

from flocker.node._docker import Unit

from .utils import running_units, require_installed, get_nodes


class DeploymentTests(TestCase):
    """
    Tests for deploying applications.

    Similar to http://doc-dev.clusterhq.com/gettingstarted/tutorial/
    moving-applications.html#starting-an-application
    """
    @require_installed
    def setUp(self):
        pass

    def test_deploy(self):
        """
        Call a 'deploy' utility function with an application and deployment
        config and watch docker ps output.
        """
        node_1, node_2 = get_nodes(num_nodes=2)

        temp = FilePath(self.mktemp())
        temp.makedirs()

        application_config = temp.child(b"application.yml")
        application_config.setContent(safe_dump({
            u"version": 1,
            u"applications": {
                u"mongodb-example": {
                    u"image": u"clusterhq/mongodb",
                },
            },
        }))

        deployment_config = temp.child(b"deployment.yml")
        deployment_config.setContent(safe_dump({
            u"version": 1,
            u"nodes": {
                node_1: [u"mongodb-example"],
                node_2: [],
            },
        }))

        # How do we specify that the containers should be priviledged (so as
        # to be able to be run inside another docker container)
        check_output([b"flocker-deploy"] +
                     [deployment_config.path] +
                     [application_config.path])

        expected = set([
            Unit(name=u'/mongodb-example-data',
                 container_name=u'/mongodb-example-data',
                 activation_state=u'inactive',
                 container_image=u'clusterhq/mongodb:latest',
                 ports=frozenset(), environment=None, volumes=())
        ])

        running = {
            node_1: running_units(node_1),
            node_2: running_units(node_2),
        }

        self.assertEqual(
            running,
            {
                node_1: expected,
                node_2: set(),
            }
        )
