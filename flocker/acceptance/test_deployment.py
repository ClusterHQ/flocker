# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for deploying applications.
"""
from twisted.internet.defer import gatherResults

from twisted.trial.unittest import TestCase

from flocker.node._docker import BASE_NAMESPACE, Unit

from .utils import (flocker_deploy, get_nodes, RemoteDockerClient,
                    require_flocker_cli)


class DeploymentTests(TestCase):
    """
    Tests for deploying applications.

    Similar to:
    http://doc-dev.clusterhq.com/gettingstarted/tutorial/
    moving-applications.html#starting-an-application
    """
    @require_flocker_cli
    def test_deploy(self):
        """
        Deploying an application to one node and not another puts the
        application where expected. Where applicable, Docker has internal
        representations of the data given by the configuration files supplied
        to flocker-deploy.
        """
        d = get_nodes(num_nodes=2)

        def deploy(node_ips):
            node_1, node_2 = node_ips

            application = u"mongodb-example"
            image = u"clusterhq/mongodb"

            # TODO change this and other variables to be similar to tutorial
            # yml files
            application_config = {
                u"version": 1,
                u"applications": {
                    application: {
                        u"image": image,
                    },
                },
            }

            deployment_config = {
                u"version": 1,
                u"nodes": {
                    node_1: [application],
                    node_2: [],
                },
            }

            flocker_deploy(self, deployment_config, application_config)

            # TODO github.com/ClusterHQ/flocker/pull/897#discussion_r19024229
            # This assertion setup code is very similar to the one in previous
            # test; probably we can make utility assertion function that
            # covers both cases.
            unit = Unit(name=application,
                        container_name=BASE_NAMESPACE + application,
                        activation_state=u'active',
                        container_image=image + u':latest',
                        ports=frozenset(), environment=None, volumes=())

            d = gatherResults([RemoteDockerClient(node_1).list(),
                               RemoteDockerClient(node_2).list()])

            def listed(units):
                node_1_list, node_2_list = units
                self.assertEqual([set([unit]), set()],
                                 [node_1_list, node_2_list])

            d.addCallback(listed)
            return d

        d.addCallback(deploy)
        return d
