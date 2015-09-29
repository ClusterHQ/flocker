# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for restarting and reboots and their interactions.
"""

from subprocess import call

from twisted.trial.unittest import TestCase, FailTest

from treq import get, content

from ...testtools import loop_until, random_name
from ..testtools import create_dataset, require_cluster
from ...common.runner import run_ssh
from ..scripts import SCRIPTS


def _service(address, name, action):
    """
    :param bytes address: The public IP of the node on which the service will
        be changed.
    :param bytes action: The action to perform on the service.
    """
    from twisted.internet import reactor
    command = ["systemctl", action, name]
    d = run_ssh(reactor, b"root", address, command)

    def handle_error(_, action):
        raise FailTest(
            "{} failed. See logs for process output.".format(
                command
            )
        )

    d.addErrback(handle_error, action)
    return d


class RebootTests(TestCase):
    """
    Tests for rebooting machines.
    """
    @require_cluster(2)
    def test_restart_always_reboot_with_dataset(self, cluster):
        """
        If a container has a volume mapped to a dataset, on reboots it will
        only be restarted after the volume becomes available.

        This test is designed to catch the following bug:
        * Server reboots.
        * Container agent starts before dataset agent has reported its state.
        * On connecting to control service it receives stale dataset state from
          before the reboot. (The stale state wiper has not yet purged the
          stale dataset state)
        * Container agent acts on this state by starting a container.
        * Docker finds the (unmounted) /flocker/<dataset_id> subdirectory from
          before the reboot.
        * Stateful application appears to have lost its data, because it only
          sees the local directory on the host, not the mounted dataset.

        We record the uptime to a file in the /data directory if the file does
        not already exist.
        If backed by a dataset, the uptime should be recorded once and then
        reported every time the container is started with that dataset.
        If the container starts before the dataset is mounted, the uptime will
        be different when the container is started after a reboot.
        We force the situation by disabling the dataset-agent before rebooting.

        The test fails as follows when run against master:

        ```
        ./admin/run-acceptance-tests --keep --distribution=centos-7 --provider=aws --dataset-backend=aws --config-file=$PWD/acceptance.yml --branch=master --flocker-version='' flocker.acceptance.endtoend.test_restarts

        ...

        [FAIL]
        Traceback (most recent call last):
          File "/home/richard/projects/HybridLogic/flocker/flocker/acceptance/endtoend/test_restarts.py", line 142, in got_rebooted_response
            preserved_initial_reboot_time)
          File "/home/richard/.virtualenvs/3137/lib/python2.7/site-packages/twisted/trial/_synctest.py", line 447, in assertEqual
            % (msg, pformat(first), pformat(second)))
        twisted.trial.unittest.FailTest: not equal:
        a = '2015-09-28 18:11:35'
        b = '2015-09-28 18:35:59'

        flocker.acceptance.endtoend.test_restarts.RebootTests.test_restart_always_reboot_with_dataset
        -------------------------------------------------------------------------------
        Ran 1 tests in 167.584s
        ```

        With the fix, this test will simply time out because the container will
        never start.
        So after rebooting we plan to poll the control service until we get an
        empty application state then restart the flocker-dataset agent and poll
        until the reboot_httpserver responds with the original uptime and
        container ID. i.e.
         * The container is only restarted once the dataset agent reports its
           state.
         * And the container is *re-started* rather than a new container being
           started.
        """
        # Find a node which is not running the control service.
        # If the control node is rebooted, we won't get stale dataset state.
        node = [node for node in cluster.nodes if
                node.public_address != cluster.control_node.public_address][0]
        print "OPERATING ON:", node

        # Create a dataset on non-control node.
        creating_dataset = create_dataset(self, cluster, node=node)

        def query_server():
            req = get(
                "http://{host}:12345".format(host=node.public_address),
                persistent=False
            ).addCallbacks(content)
            return req

        def created_dataset(dataset):
            print "DATASET", dataset
            http_server = {
                u"name": random_name(self),
                u"node_uuid": str(node.uuid),
                u"image": u"python:2.7-slim",
                u"ports": [{u"internal": 12345, u"external": 12345}],
                u"volumes": [{u"dataset_id": str(dataset.dataset_id),
                              u"mountpoint": u"/data"}],
                u"command_line": [u"python", u"-c",
                                  SCRIPTS.child(
                                      b"reboot_httpserver.py"
                                  ).getContent().decode("ascii"),
                                  u"/data"],
            }
            # Start a container on non-control node.
            # The container has a web server that saves state to the dataset
            # created earlier.
            created = cluster.create_container(http_server)
            created.addCallback(lambda _: self.addCleanup(
                cluster.remove_container, http_server[u"name"]))
            # Continue when the server has responded to an HTTP request.
            created.addCallback(lambda _:
                                loop_until(lambda: query_server().addErrback(
                                    lambda _: False)))
            created.addCallback(lambda _: query_server())
            return created
        starting_server = creating_dataset.addCallback(created_dataset)

        def server_started(initial_response):
            # We now have the initial response of the server. This should
            # be the initial boot time of the node, repeated twice.  Next,
            # we restart the machine.
            print "INITIAL RESPONSE", initial_response
            initial_reboot_time = initial_response.splitlines()[0]
            initial_container_id = initial_response.splitlines()[2]
            initial_container_id = initial_container_id.encode("ascii")

            # Disable the dataset-agent before rebooting
            disabling = _service(
                node.public_address, b'flocker-dataset-agent', b'disable'
            )

            # Reboot the server once the dataset agent has been disabled.
            def reboot(ignored):
                # XXX Checking exit code is problematic insofar as reboot
                # kills the ssh process...
                print "Rebooting!"
                call([b"ssh", b"root@{}".format(node.public_address),
                      b"shutdown", b"-r", b"now"])
            rebooting = disabling.addCallback(reboot)

            # Final implementation will:
            # * poll control service for empty application state here, then
            # * re-enable and restart the dataset-agent.

            # Now, keep trying to get a response until it's different than
            # the one we originally got, thus indicating a reboot:
            def query_until_different():
                print "query!"
                return query_server().addCallbacks(
                    lambda response: response != initial_response,
                    lambda _: False)

            rebooted = rebooting.addCallback(
                lambda _: loop_until(query_until_different)
            )

            querying = rebooted.addCallback(lambda _: query_server())

            # Now that we've rebooted, we expect first line to be
            # unchanged (i.e. preserved across reboots in the volume):
            def got_rebooted_response(second_response):
                print "SECOND RESPONSE", second_response
                preserved_initial_reboot_time = second_response.splitlines()[0]
                new_container_id = second_response.splitlines()[2]
                self.assertEqual(initial_reboot_time,
                                 preserved_initial_reboot_time)
                self.assertNotEqual(initial_container_id, new_container_id)
            querying.addCallback(got_rebooted_response)
            return querying
        creating_dataset.addCallback(server_started)
        return creating_dataset

    # Reboots can take a while:
    test_restart_always_reboot_with_dataset.timeout = 480
