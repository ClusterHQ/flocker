# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for interoperability between MongoDB and Flocker datasets.
"""

from datetime import timedelta

from twisted.python.filepath import FilePath

from ..testtools import get_mongo_client, require_mongo
from .testtools import make_dataset_integration_testcase

from ...testtools import async_runner


def insert_data(test_case, host, port):
    """
    Insert some data into the database.

    :param TestCase test_case: A test.
    :param host: Host to connect to.
    :param port: Port to connect to.

    :return: ``Deferred`` that fires when data has been inserted.
    """
    d = get_mongo_client(host, port)

    def got_client(client):
        database = client.example
        database.posts.insert({u"the data": u"it moves"})
    d.addCallback(got_client)
    return d


def assert_inserted(test_case, host, port):
    """
    Verify some data has been inserted into the database.

    :param TestCase test_case: A test.
    :param host: Host to connect to.
    :param port: Port to connect to.

    :return: ``Deferred`` that fires when we verify data has been inserted.
    """
    d = get_mongo_client(host, port)

    def got_client(client):
        database = client.example
        data = database.posts.find_one()
        test_case.assertEqual(data[u"the data"], u"it moves")

    d.addCallback(got_client)
    return d


class MongoIntegrationTests(make_dataset_integration_testcase(
        u"clusterhq/mongodb", FilePath(b"/data/db"), 27017,
        insert_data, assert_inserted,
        )):
    """
    Integration tests for MongoDB.
    """

    # Disable timeout for MongoDB integration tests.
    run_tests_with = async_runner(timeout=timedelta(hours=1))

    @require_mongo
    def setUp(self):
        super(MongoIntegrationTests, self).setUp()
