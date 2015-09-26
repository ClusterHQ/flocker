# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for restarting and reboots and their interactions.
"""

from subprocess import call
from unittest import SkipTest

from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase

from treq import get, content

from ..testtools import loop_until, random_name
from .testtools import create_dataset, require_cluster


REBOOT_SERVER = FilePath(__file__).sibling(b"reboot_httpserver.py")


class RestartTests(TestCase):
    """
    Tests for restart policies.
    """
    @require_cluster(1)
    def test_restart_always_reboot_with_dataset(self, cluster):
        """
        If a container has a restart policy of ``always`` and a volume mapped
        to a dataset, on reboots it will only be restarted after the
        volume becomes available.
        """
        #raise SkipTest("Don't want to run this on buildbot, for now at least.")
        node = cluster.nodes[0]
        # Implicitly uses first node:
        creating_dataset = create_dataset(self, cluster)

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
                u"node_uuid": str(cluster.nodes[0].uuid),
                u"image": u"python:2.7-slim",
                u"ports": [{u"internal": 12345, u"external": 12345}],
                # We expect restarts to occur after reboot with this policy:
                u'restart_policy': {u'name': u'always'},
                u"volumes": [{u"dataset_id": dataset.dataset_id,
                              u"mountpoint": u"/data"}],
                u"command_line": [u"python", u"-c",
                                  REBOOT_SERVER.getContent().decode("ascii"),
                                  u"/data"],
            }
            created = cluster.create_container(http_server)
            created.addCallback(lambda _: self.addCleanup(
                cluster.remove_container, http_server[u"name"]))
            created.addCallback(lambda _:
                                loop_until(lambda: query_server().addErrback(
                                    lambda _: False)))
            created.addCallback(lambda _: query_server())
            return created
        creating_dataset.addCallback(created_dataset)

        def server_started(initial_response):
            # We now have the initial response of the server. This should
            # be the initial boot time of the node, repeated twice.  Next,
            # we restart the machine.
            print "INITIAL RESPONSE", initial_response
            initial_reboot_time = initial_response.splitlines()[0]
            # XXX Checking exit code is problematic insofar as reboot
            # kills the ssh process...
            print "Rebooting!"
            call([b"ssh", b"root@{}".format(node.public_address),
                  b"shutdown", b"-r", b"now"])
            # Now, keep trying to get a response until it's different than
            # the one we originally got, thus indicating a reboot:

            def query_until_different():
                print "query!"
                return query_server().addCallbacks(
                    lambda response: response != initial_response,
                    lambda _: False)
            rebooted = loop_until(query_until_different)
            rebooted.addCallback(lambda _: query_server())

            # Now that we've rebooted, we expect first line to be
            # unchanged (i.e. preserved across reboots in the volume):
            def got_rebooted_response(second_response):
                print "SECOND RESPONSE", second_response
                preserved_initial_reboot_time = second_response.splitlines()[0]
                self.assertEqual(initial_reboot_time,
                                 preserved_initial_reboot_time)
            rebooted.addCallback(got_rebooted_response)
            return rebooted
        creating_dataset.addCallback(server_started)
        return creating_dataset

    # Reboots can take a while:
    test_restart_always_reboot_with_dataset.timeout = 480
