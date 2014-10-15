# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for movement of data across nodes.
"""
from yaml import safe_dump

from pexpect import spawn

from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase

from .utils import (flocker_deploy, get_nodes, require_flocker_cli,
                    require_mongo)


class MovingDataTests(TestCase):
    """
    Tests for movement of data across nodes.

    Similar to:
        http://doc-dev.clusterhq.com/gettingstarted/tutorial/volumes.html
    """
    @require_mongo
    @require_flocker_cli
    def test_moving_data(self):
        """
        Moving an application moves that application's data with it.

        Instead of pexpect this could use PyMongo, which would mean that the
        mongo client would not have to be installed. However, this uses
        pexpect to be as close as possible to the tutorial.
        """
        node_1, node_2 = get_nodes(num_nodes=2)

        temp = FilePath(self.mktemp())
        temp.makedirs()

        application = u"mongodb-volume-example"

        application_config = temp.child(b"application.yml")
        application_config.setContent(safe_dump({
            u"version": 1,
            u"applications": {
                application: {
                    u"image": u"clusterhq/mongodb",
                    u"ports": [{
                        u"internal": 27017,
                        u"external": 27017,
                    }],
                    u"volume": {
                        # The location within the container where the data
                        # volume will be mounted:
                        u"mountpoint": u"/data/db"
                    }
                },
            },
        }))

        deployment_config = temp.child(b"deployment.yml")
        deployment_config.setContent(safe_dump({
            u"version": 1,
            u"nodes": {
                node_1: [application],
                node_2: [],
            },
        }))

        flocker_deploy(deployment_config, application_config)

        child_1 = spawn('mongo ' + node_1)
        child_1.expect('MongoDB shell version:.*')
        child_1.sendline('use example;')
        child_1.expect('switched to db example')
        child_1.sendline('db.records.insert({"the data": "it moves"})')

        deployment_moved_config = temp.child(b"volume-deployment-moved.yml")
        deployment_moved_config.setContent(safe_dump({
            u"version": 1,
            u"nodes": {
                node_1: [],
                node_2: [application],
            },
        }))

        flocker_deploy(deployment_moved_config, application_config)

        child_2 = spawn('mongo ' + node_2)
        # The docs say "If you get a connection refused error try again after
        # a few seconds; the application might take some time to fully start
        # up.". If this problem manifests here, program that with an except
        # clause.
        child_2.expect('MongoDB shell version:.*')
        child_2.sendline('use example;')
        child_2.expect('switched to db example')
        child_2.sendline('db.records.insert({"the data": "it moves"})')
        child_2.sendline('db.records.find({})')
        child_2.expect('{ "_id" : ObjectId\(".*"\), "the data" : "it moves" }')
