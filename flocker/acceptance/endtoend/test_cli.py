# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for the ``flocker-deploy`` command line tool.
"""

from twisted.trial.unittest import TestCase

from ..testtools import require_flocker_cli, require_cluster
from ...testtools import random_name


class FlockerDeployTests(TestCase):
    """
    Tests for ``flocker-deploy``.
    """
    @require_flocker_cli
    @require_cluster(1)
    def test_deploy(self, cluster):
        """
        Deploying an application to one node and not another puts the
        application where expected.
        """
        [node_1] = cluster.nodes
        name = random_name(self)

        minimal_deployment = {
            u"version": 1,
            u"nodes": {
                node_1.reported_hostname: [name],
            },
        }

        minimal_application = {
            u"version": 1,
            u"applications": {
                name: {
                    # Our config format doesn't support command-lines, so
                    # we can't use standard image and need to pick
                    # something small that will not immediately exit.
                    u"image": u"openshift/busybox-http-app",
                },
            },
        }

        # flocker_deploy() does an assertion that the requested state has
        # been reached. Once remaining uses of flocker_deploy elsewhere
        # are removed that code could be moved off of Cluster and into
        # this module since this is only module we expect will be calling
        # flocker-deploy.
        d = cluster.flocker_deploy(
            self, minimal_deployment, minimal_application)
        d.addCallback(lambda _:
                      self.addCleanup(cluster.remove_container, name))
        return d
