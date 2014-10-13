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


from .utils import running_units, require_installed, get_node_ips


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
        node_1_ip, node_2_ip = get_node_ips()
        containers_running_before = running_units(node_1_ip)

        temp = FilePath(self.mktemp())
        temp.makedirs()

        application_config_path = temp.child(b"application.yml")
        application_config_path.setContent(safe_dump({
            u"version": 1,
            u"applications": {
                u"mongodb-example": {
                    u"image": u"clusterhq/mongodb",
                },
            },
        }))

        deployment_config_path = temp.child(b"deployment.yml")
        deployment_config_path.setContent(safe_dump({
            u"version": 1,
            u"nodes": {
                node_1_ip: [u"mongodb-example"],
                node_2_ip: [],
            },
        }))

        # How do we specify that the containers should be priviledged (so as
        # to be able to be run inside another docker container)
        check_output([b"flocker-deploy"] +
                     [deployment_config_path.path] +
                     [application_config_path.path])

        containers_running_after = running_units(node_1_ip)

        new_containers = (set(containers_running_after) -
                          set(containers_running_before))

        expected = set([Unit(name=u'mongodb-example-data',
                             container_name=u'mongodb-example-data',
                             activation_state=u'active',
                             container_image=u'clusterhq/mongodb:latest',
                             ports=(), environment=None, volumes=())])

        self.assertEqual(new_containers, expected)
