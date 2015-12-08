# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for the control service REST API.
"""

from json import loads, dumps
from time import sleep
from datetime import timedelta

from testtools import run_test_with

from twisted.internet import reactor
from twisted.internet.defer import gatherResults
from twisted.internet.error import ProcessTerminated

from ...common import loop_until
from ...testtools import AsyncTestCase, async_runner, flaky, random_name
from ..testtools import (
    require_cluster, require_moving_backend, create_dataset,
    create_python_container, verify_socket, post_http_server,
    assert_http_server, query_http_server
)
from ..scripts import SCRIPTS


class ContainerAPITests(AsyncTestCase):
    """
    Tests for the container API.
    """
    def _create_container(self, cluster, script):
        """
        Create a container listening on port 8080.

        :return: ``Deferred`` firing with a container dictionary once the
            container is up and running.
        """
        d = create_python_container(
            self, cluster, {
                u"ports": [{u"internal": 8080, u"external": 8080}],
                u"node_uuid": cluster.nodes[0].uuid,
            }, script)

        def check_result(response):
            dl = verify_socket(cluster.nodes[0].public_address, 8080)
            dl.addCallback(lambda _: response)
            return dl

        d.addCallback(check_result)
        return d

    @require_cluster(1)
    def test_create_container_with_ports(self, cluster):
        """
        Create a container including port mappings on a single-node cluster.
        """
        return self._create_container(cluster, SCRIPTS.child(b"hellohttp.py"))

    @require_cluster(1)
    def test_create_container_restart_stopped(self, cluster):
        """
        A container is restarted if it is stopped.
        """
        responses = []

        def query_and_save():
            querying = query_http_server(
                cluster.nodes[0].public_address, 8080
            )
            querying.addCallback(responses.append)
            return querying

        created = self._create_container(
            cluster, SCRIPTS.child(b"exitinghttp.py")
        )

        # `query_http_server` will kill the server first time round.
        created.addCallback(lambda ignored: query_and_save())

        # Call it again and see that the container is running again.
        created.addCallback(lambda ignored: query_and_save())

        # Verify one of the assumptions ... That the container restarted in
        # between requests.  exitinghttp.py gives back a process-unique random
        # value as the response body.
        def check_different_response(ignored):
            self.assertNotEqual(
                responses[0],
                responses[1],
                "Responses to two requests were the same, "
                "container probably did not restart.",
            )
        created.addCallback(check_different_response)

        return created

    @require_cluster(1)
    def test_create_container_with_environment(self, cluster):
        """
        If environment variables are specified when creating a container,
        those variables are available in the container's environment.
        """
        environment = {u"XBLOO": u"YBLAH", u"ZBLOO": u"ZEBRA"}

        d = create_python_container(
            self, cluster, {
                u"ports": [{u"internal": 8080, u"external": 8080}],
                u"node_uuid": cluster.nodes[0].uuid,
                u"environment": environment,
            }, SCRIPTS.child(b"envhttp.py"))

        def checked(_):
            host = cluster.nodes[0].public_address
            d = query_http_server(host, 8080)
            d.addCallback(lambda data: dict(loads(data)))
            return d
        d.addCallback(checked)

        d.addCallback(
            lambda response:
                self.assertDictContainsSubset(environment, response)
        )
        return d

    @flaky(u'FLOC-2488')
    @require_moving_backend
    @require_cluster(2)
    def test_move_container_with_dataset(self, cluster):
        """
        Create a container with an attached dataset, issue API call
        to move the container. Wait until we can connect to the running
        container on the new host and verify the data has moved with it.
        """
        data = {u"the data": u"it moves"}
        post_data = {"data": dumps(data)}
        node1, node2 = cluster.nodes
        container_name = random_name(self)
        creating_dataset = create_dataset(self, cluster)

        def create_container(dataset):
            d = create_python_container(
                self, cluster, {
                    u"name": container_name,
                    u"ports": [{u"internal": 8080, u"external": 8080}],
                    u"node_uuid": node1.uuid,
                    u"volumes": [{u"dataset_id": unicode(dataset.dataset_id),
                                  u"mountpoint": u"/data"}],
                }, SCRIPTS.child(b"datahttp.py"),
                additional_arguments=[u"/data"],
            )
            return d
        creating_dataset.addCallback(create_container)
        creating_dataset.addCallback(
            lambda _: post_http_server(
                self, node1.public_address, 8080, post_data)
        )

        def move_container(_):
            moved = cluster.move_container(
                container_name, node2.uuid
            )
            return moved
        creating_dataset.addCallback(move_container)
        creating_dataset.addCallback(
            lambda _: assert_http_server(
                self, node2.public_address, 8080,
                expected_response=post_data["data"])
        )

        return creating_dataset

    @require_cluster(1)
    def test_create_container_with_dataset(self, cluster):
        """
        Create a container with an attached dataset, write some data,
        shut it down, create a new container with same dataset, make sure
        the data is still there.
        """
        data = {u"the data": u"sample written data"}
        post_data = {"data": dumps(data)}
        node = cluster.nodes[0]
        container_name = random_name(self)
        creating_dataset = create_dataset(self, cluster)
        self.dataset_id = None

        def create_container(dataset):
            self.dataset_id = unicode(dataset.dataset_id)
            d = create_python_container(
                self, cluster, {
                    u"name": container_name,
                    u"ports": [{u"internal": 8080, u"external": 8080}],
                    u"node_uuid": node.uuid,
                    u"volumes": [{u"dataset_id": self.dataset_id,
                                  u"mountpoint": u"/data"}],
                }, SCRIPTS.child(b"datahttp.py"),
                additional_arguments=[u"/data"],
                cleanup=False,
            )
            return d
        creating_dataset.addCallback(create_container)
        creating_dataset.addCallback(
            lambda _: post_http_server(
                self, node.public_address, 8080, post_data)
        )
        creating_dataset.addCallback(
            lambda _: assert_http_server(
                self, node.public_address, 8080,
                expected_response=post_data["data"])
        )
        creating_dataset.addCallback(
            lambda _: cluster.remove_container(container_name))

        def create_second_container(_):
            d = create_python_container(
                self, cluster, {
                    u"ports": [{u"internal": 8080, u"external": 8081}],
                    u"node_uuid": node.uuid,
                    u"volumes": [{u"dataset_id": self.dataset_id,
                                  u"mountpoint": u"/data"}],
                }, SCRIPTS.child(b"datahttp.py"),
                additional_arguments=[u"/data"],
            )
            return d
        creating_dataset.addCallback(create_second_container)
        creating_dataset.addCallback(
            lambda _: assert_http_server(
                self, node.public_address, 8081,
                expected_response=post_data["data"])
        )
        return creating_dataset

    @require_cluster(1)
    def test_current(self, cluster):
        """
        The current container endpoint includes a currently running container.
        """
        creating = self._create_container(
            cluster, SCRIPTS.child(b"hellohttp.py")
        )

        def created(data):
            data[u"running"] = True

            def in_current():
                current = cluster.current_containers()
                current.addCallback(lambda result: data in result)
                return current
            return loop_until(reactor, in_current)
        creating.addCallback(created)
        return creating

    @require_cluster(1)
    def test_non_root_container_can_access_dataset(self, cluster):
        """
        A container running as a user that is not root can write to a
        dataset attached as a volume.
        """
        node = cluster.nodes[0]
        creating_dataset = create_dataset(self, cluster)

        def created_dataset(dataset):
            return create_python_container(
                self, cluster, {
                    u"ports": [{u"internal": 8080, u"external": 8080}],
                    u"node_uuid": node.uuid,
                    u"volumes": [{u"dataset_id": unicode(dataset.dataset_id),
                                  u"mountpoint": u"/data"}],
                }, SCRIPTS.child(b"nonrootwritehttp.py"),
                additional_arguments=[u"/data"])
        creating_dataset.addCallback(created_dataset)

        creating_dataset.addCallback(
            lambda _: assert_http_server(self, node.public_address, 8080))
        return creating_dataset

    @require_cluster(2)
    def test_linking(self, cluster):
        """
        A link from an origin container to a destination container allows the
        origin container to establish connections to the destination container
        when the containers are running on different machines using an address
        obtained from ``<ALIAS>_PORT_<PORT>_TCP_{ADDR,PORT}``-style environment
        set in the origin container's environment.
        """
        destination_port = 8080
        origin_port = 8081

        [destination, origin] = cluster.nodes

        running = gatherResults([
            create_python_container(
                self, cluster, {
                    u"ports": [{u"internal": 8080,
                                u"external": destination_port}],
                    u"node_uuid": destination.uuid,
                }, SCRIPTS.child(b"hellohttp.py")),
            create_python_container(
                self, cluster, {
                    u"ports": [{u"internal": 8081,
                                u"external": origin_port}],
                    u"links": [{u"alias": "dest", u"local_port": 80,
                                u"remote_port": destination_port}],
                    u"node_uuid": origin.uuid,
                }, SCRIPTS.child(b"proxyhttp.py")),
            # Wait for the link target container to be accepting connections.
            verify_socket(destination.public_address, destination_port),
            # Wait for the link source container to be accepting connections.
            verify_socket(origin.public_address, origin_port),
            ])

        running.addCallback(
            lambda _: assert_http_server(
                self, origin.public_address, origin_port))
        return running

    @flaky([u"FLOC-3485"])
    @require_cluster(2)
    def test_traffic_routed(self, cluster):
        """
        An application can be accessed even from a connection to a node
        which it is not running on.
        """
        port = 8080

        [destination, origin] = cluster.nodes

        running = gatherResults([
            create_python_container(
                self, cluster, {
                    u"ports": [{u"internal": 8080, u"external": port}],
                    u"node_uuid": destination.uuid,
                }, SCRIPTS.child(b"hellohttp.py")),
            # Wait for the destination to be accepting connections.
            verify_socket(destination.public_address, port),
            # Wait for the origin container to be accepting connections.
            verify_socket(origin.public_address, port),
            ])

        running.addCallback(
            # Connect to the machine where the container is NOT running:
            lambda _: assert_http_server(self, origin.public_address, port))
        return running

    # Unfortunately this test is very very slow.
    @run_test_with(async_runner(timeout=timedelta(minutes=6)))
    @require_cluster(2)
    def test_reboot(self, cluster):
        """
        After a reboot the containers are only started once all datasets are
        available locally.

        We disable the dataset agent during reboot in order to ensure as
        much as possible that the container agent gets stale data from the
        control service.
        """
        # Find a node which is not running the control service.
        # If the control node is rebooted, we won't get stale dataset state.
        node = [node for node in cluster.nodes if
                node.public_address != cluster.control_node.public_address][0]

        def query():
            d = query_http_server(node.public_address, 8080)
            d.addCallback(loads)
            return d

        creating_dataset = create_dataset(self, cluster, node=node)

        def created_dataset(dataset):
            return create_python_container(
                self, cluster, {
                    u"ports": [{u"internal": 8080, u"external": 8080}],
                    u"node_uuid": node.uuid,
                    u"volumes": [{u"dataset_id": unicode(dataset.dataset_id),
                                  u"mountpoint": u"/data"}],
                }, SCRIPTS.child(b"remember_boot_id.py"),
                additional_arguments=[u"/data"])
        creating_dataset.addCallback(created_dataset)

        creating_dataset.addCallback(lambda _: query())

        def got_initial_result(initial_result):
            self.addCleanup(node.run_script, "enable_service",
                            "flocker-dataset-agent")
            # Disable the service to force container agent to always get stale
            # data from the container agent:
            d = node.run_script("disable_service", "flocker-dataset-agent")
            d.addCallback(lambda _: node.reboot())
            # Wait for reboot to be far enough along that everything
            # should be shutdown:
            d.addCallback(lambda _: sleep(20))
            # Wait until server is back up:
            changed = d.addCallback(lambda _:
                                    verify_socket(node.public_address, 22))

            # Wait until container agent is back up:
            def container_agent_running():
                # pidof will return the pid if flocker-container-agent is
                # running else exit with status 1 which triggers the
                # errback chain.
                command = [b'pidof', b'-x', b'flocker-container-agent']
                d = node.run_as_root(command)

                def not_existing(failure):
                    failure.trap(ProcessTerminated)
                    return False
                d.addCallbacks(lambda result: True, not_existing)
                return d
            changed.addCallback(
                lambda _: loop_until(reactor, container_agent_running))

            # Start up dataset agent so container agent can proceed:
            def up_again(_):
                # Give it a few seconds for container agent to get stale data
                # from control service:
                sleep(10)
                # Now start up dataset agent again:
                return node.run_script(
                    "enable_service", "flocker-dataset-agent")
            changed.addCallback(up_again)

            changed.addCallback(lambda _: loop_until(
                reactor, lambda: query().addCallback(
                    lambda result: result != initial_result)))
            changed.addCallback(lambda _: query())

            def result_changed(new_result):
                self.assertEqual(
                    dict(current_same=(new_result["current"] ==
                                       initial_result["current"]),
                         written_same=(new_result["written"] ==
                                       initial_result["written"])),
                    dict(current_same=False,  # post-reboot expect new boot_id
                         written_same=True,  # written data survived reboot
                         ))
            changed.addCallback(result_changed)
            return changed

        creating_dataset.addCallback(got_initial_result)
        return creating_dataset
