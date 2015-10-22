# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for the ``flocker-deploy`` command line tool.
"""

from copy import deepcopy
from subprocess import check_call

from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase
from yaml import safe_dump

from ...control._config import FlockerConfiguration
from ...control.httpapi import container_configuration_response

from ..testtools import require_flocker_cli, require_cluster
from ...testtools import loop_until, random_name


class FlockerDeployTests(TestCase):
    """
    Tests for ``flocker-deploy``.
    """
    def flocker_deploy(self, cluster, deployment_config, application_config):
        """
        Run ``flocker-deploy`` with given configuration files.

        :param cluster: The ``Cluster`` to which the supplied config should
            be applied.
        :param dict deployment_config: The desired deployment configuration.
        :param dict application_config: The desired application configuration.
        """
        # Construct an expected deployment mapping of IP addresses
        # to a set of ``Application`` instances.
        applications_to_parse = deepcopy(application_config)
        expected_deployment = dict()
        applications_map = FlockerConfiguration(
            applications_to_parse).applications()
        for node in deployment_config['nodes']:
            node_applications = []
            for node_app in deployment_config['nodes'][node]:
                if node_app in applications_map:
                    node_applications.append(applications_map[node_app])
            expected_deployment[node] = set(node_applications)
        temp = FilePath(self.mktemp())
        temp.makedirs()

        deployment = temp.child(b"deployment.yml")
        deployment.setContent(safe_dump(deployment_config))

        application = temp.child(b"application.yml")
        application.setContent(safe_dump(application_config))
        check_call([b"flocker-deploy",
                    b"--certificates-directory",
                    cluster.certificates_path.path,
                    cluster.control_node.public_address,
                    deployment.path, application.path])
        # Wait for the cluster state to match the new deployment.
        da = self.assert_expected_deployment(cluster, expected_deployment)
        return da

    def assert_expected_deployment(self, cluster, expected_deployment):
        """
        Assert that the expected set of ``Application`` instances on a set of
        nodes is the same as the actual set of ``Application`` instance on
        those nodes.

        The tutorial looks at Docker output, but the acceptance tests are
        intended to test high-level external behaviors. Since this is looking
        at the output of the control service API it merely verifies what
        Flocker believes the system state is, not the actual state.
        The latter should be verified separately with additional tests
        for external side-effects (applications being available on ports,
        say).

        :param cluster: The ``Cluster`` to query for current configuration.
        :param dict expected_deployment: A mapping of IP addresses to set of
            ``Application`` instances expected on the nodes with those IP
            addresses.

        :return Deferred: Fires on end of assertion.
        """
        ip_to_uuid = {
            node.reported_hostname: node.uuid for node in cluster.nodes
        }

        def got_results(existing_containers):
            expected = []
            for reported_hostname, apps in expected_deployment.items():
                node_uuid = ip_to_uuid[reported_hostname]
                expected += [container_configuration_response(app, node_uuid)
                             for app in apps]
            for app in expected:
                app[u"running"] = True
            return sorted(existing_containers) == sorted(expected)

        def configuration_matches_state():
            d = cluster.current_containers()
            d.addCallback(got_results)
            return d

        return loop_until(configuration_matches_state)

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

        d = self.flocker_deploy(
            cluster, minimal_deployment, minimal_application)
        d.addCallback(lambda _:
                      self.addCleanup(cluster.remove_container, name))
        return d
