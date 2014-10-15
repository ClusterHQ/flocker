# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for movement of data across nodes.
"""
from unittest import skipUnless
from yaml import safe_dump

from pexpect import spawn

from twisted.python.filepath import FilePath
from twisted.python.procutils import which
from twisted.trial.unittest import TestCase

from flocker.node._docker import Unit, PortMap

from .utils import running_units, require_installed, get_nodes, flocker_deploy


class DataTests(TestCase):
    """
    Tests for movement of data across nodes.

    Similar to http://doc-dev.clusterhq.com/gettingstarted/tutorial/
    volumes.html
    """
    # TODO Require mongo - make this a utlity function
    def test_data_moves(self):
        """
        Moving an application moves data with it.

        Instead of pexpect this could use PyMongo, which would mean that the
        mongo client would not have to be installed. However, this uses
        pexpect to be as close as possible to the tutorial.
        """
        # TODO remove all the 'self's
        self.node_1, self.node_2 = get_nodes(num_nodes=2)

        temp = FilePath(self.mktemp())
        temp.makedirs()

        self.internal_port = 27017
        self.external_port = 27017

        self.application = u"mongodb-volume-example"
        self.image = u"clusterhq/mongodb"

        application_config = temp.child(b"application.yml")
        application_config.setContent(safe_dump({
            u"version": 1,
            u"applications": {
                self.application: {
                    u"image": self.image,
                    u"ports": [{
                        u"internal": self.internal_port,
                        u"external": self.external_port,
                    }],
                    u"volume":
                          # The location within the container where the data volume will be
                          # mounted:
                          u"mountpoint": u"/data/db"
                },
            },
        }))

        deployment_config = temp.child(b"deployment.yml")
        deployment_config.setContent(safe_dump({
            u"version": 1,
            u"nodes": {
                self.node_1: [self.application],
                self.node_2: [],
            },
        }))

        flocker_deploy(deployment_config, application_config)

        child_1 = spawn('mongo ' + self.node_1)
        child_1.expect('MongoDB shell version:.*')
        child_1.sendline('use example;')
        child_1.expect('switched to db example')
        child_1.sendline('db.records.insert({"the data": "it moves"})')
        child_1.sendline('db.records.find({})')
        # TODO the below is the wrong expectation
        child_1.expect('switched to db example')
        child_1.expect('{ "_id" : ObjectId\(".*"\), "the data" : "it moves" }')

        deployment_moved_config = temp.child(b"volume-deployment-moved.yml")
        deployment_moved_config.setContent(safe_dump({
            u"version": 1,
            u"nodes": {
                self.node_1: [],
                self.node_2: [self.application],
            },
        }))

        flocker_deploy(deployment_moved_config, application_config)

        child_2 = spawn('mongo ' + self.node_2)
        child_2.expect('MongoDB shell version:.*')
        child_2.sendline('use example;')
        child_2.expect('switched to db example')
        child_2.sendline('db.records.insert({"the data": "it moves"})')
        child_2.sendline('db.records.find({})')
        # TODO the below is the wrong expectation, expect the previously
        # captured output
        child_2.expect('switched to db example')
