# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for environment variables.
"""
from unittest import skipUnless
from uuid import uuid4

from eliot import Message, Logger

from pyrsistent import freeze, thaw

from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase
from twisted.internet.defer import succeed

from flocker.control import (
    Application, DockerImage, AttachedVolume, Port, Dataset,
    Manifestation)
from ..control.httpapi import container_configuration_response
from flocker.testtools import loop_until

from .testtools import (
    assert_expected_deployment, flocker_deploy,
    require_flocker_cli, require_cluster)

try:
    from pymysql import connect
    from pymysql.err import Error
    PYMYSQL_INSTALLED = True
except ImportError:
    PYMYSQL_INSTALLED = False

MYSQL_INTERNAL_PORT = 3306
MYSQL_EXTERNAL_PORT = 3306

MYSQL_PASSWORD = u"clusterhq"
MYSQL_APPLICATION_NAME = u"mysql-volume-example"
MYSQL_IMAGE = u"mysql:5.6.17"
MYSQL_ENVIRONMENT = {"MYSQL_ROOT_PASSWORD": MYSQL_PASSWORD}
MYSQL_VOLUME_MOUNTPOINT = u'/var/lib/mysql'

MYSQL_APPLICATION = Application(
    name=MYSQL_APPLICATION_NAME,
    image=DockerImage.from_string(MYSQL_IMAGE),
    environment=MYSQL_ENVIRONMENT,
    ports=frozenset([
        Port(internal_port=MYSQL_INTERNAL_PORT,
             external_port=MYSQL_EXTERNAL_PORT),
    ]),
    volume=AttachedVolume(
        manifestation=Manifestation(
            dataset=Dataset(
                dataset_id=unicode(uuid4())),
            primary=True),
        mountpoint=FilePath(MYSQL_VOLUME_MOUNTPOINT),
    ),
)

require_pymysql = skipUnless(
    PYMYSQL_INSTALLED, "PyMySQL not installed")


class EnvironmentVariableTests(TestCase):
    """
    Tests for passing environment variables to containers, in particular
    passing a root password to MySQL.
    """
    @require_flocker_cli
    @require_cluster(num_nodes=2)
    def setUp(self, cluster):
        """
        Deploy MySQL to one of two nodes.
        """
        self.cluster = cluster
        (self.node_1, self.node_1_uuid), (self.node_2, self.node_2_uuid) = [
            (node.address, node.uuid) for node in cluster.nodes]

        getting_nodes = succeed(None)

        def deploy_mysql(_):
            mysql_deployment = {
                u"version": 1,
                u"nodes": {
                    self.node_1: [MYSQL_APPLICATION_NAME],
                    self.node_2: [],
                },
            }

            self.mysql_deployment_moved = {
                u"version": 1,
                u"nodes": {
                    self.node_1: [],
                    self.node_2: [MYSQL_APPLICATION_NAME],
                },
            }

            self.mysql_application = {
                u"version": 1,
                u"applications": {
                    MYSQL_APPLICATION_NAME: {
                        u"image": MYSQL_IMAGE,
                        u"environment": MYSQL_ENVIRONMENT,
                        u"ports": [{
                            u"internal": MYSQL_INTERNAL_PORT,
                            u"external": MYSQL_EXTERNAL_PORT,
                        }],
                        u"volume": {
                            u"dataset_id":
                                MYSQL_APPLICATION.volume.dataset.dataset_id,
                            u"mountpoint": MYSQL_VOLUME_MOUNTPOINT,
                        },
                    },
                },
            }

            self.mysql_application_different_port = thaw(freeze(
                self.mysql_application).transform(
                    [u"applications", MYSQL_APPLICATION_NAME, u"ports", 0,
                     u"external"], MYSQL_EXTERNAL_PORT + 1))
            flocker_deploy(self, mysql_deployment, self.mysql_application)

        deploying_mysql = getting_nodes.addCallback(deploy_mysql)
        return deploying_mysql

    def test_deploy(self):
        """
        The test setUp deploys MySQL.
        """
        d = assert_expected_deployment(self, {
            self.node_1: set([MYSQL_APPLICATION]),
            self.node_2: set([]),
        })

        return d

    def test_moving_mysql(self):
        """
        It is possible to move MySQL to a new node.
        """
        flocker_deploy(self, self.mysql_deployment_moved,
                       self.mysql_application)

        asserting_mysql_moved = assert_expected_deployment(self, {
            self.node_1: set([]),
            self.node_2: set([MYSQL_APPLICATION]),
        })

        return asserting_mysql_moved

    def _get_mysql_connection(self, host, port, user, passwd, db=None):
        """
        Returns a ``Deferred`` which fires with a PyMySQL connection when one
        has been created.

        Parameters are passed directly to PyMySQL:
        https://github.com/PyMySQL/PyMySQL

        Raise any exceptions thrown when failing to connect if they indicate
        that MySQL has started.
        """
        expected_container = container_configuration_response(
            MYSQL_APPLICATION, self.node_1_uuid)
        waiting_for_cluster = succeed(self.cluster)

        def got_cluster(cluster):
            waiting_for_container = cluster.wait_for_container(
                expected_container
            )

            def mysql_connect(result):
                def mysql_can_connect():
                    try:
                        return connect(
                            host=host,
                            port=port,
                            user=user,
                            passwd=passwd,
                            db=db,
                        )
                    except Error as e:
                        Message.new(
                            message_type="acceptance:mysql_connect_error",
                            error=str(e)).write(Logger())
                        return False
                dl = loop_until(mysql_can_connect)
                return dl
            waiting_for_container.addCallback(mysql_connect)
            return waiting_for_container

        waiting_for_cluster.addCallback(got_cluster)
        return waiting_for_cluster

    @require_pymysql
    def test_environment_variable_used(self):
        """
        MySQL can be accessed using the root password passed in as an
        environment variable.
        """
        return self._get_mysql_connection(
            host=self.node_1,
            port=MYSQL_EXTERNAL_PORT,
            user=b'root',
            passwd=MYSQL_PASSWORD,
        )
        # No assertion, since _get_mysql_connection will fire with a failure,
        # if the credentials are incorrect.

    @require_pymysql
    def test_moving_data(self):
        """
        After adding data to MySQL and then moving it to another node, the data
        added is available on the second node.
        """
        user = b'root'
        database = b'example'

        getting_mysql = self._get_mysql_connection(
            host=self.node_1,
            port=MYSQL_EXTERNAL_PORT,
            user=user,
            passwd=MYSQL_PASSWORD,
        )

        def add_data_node_1(connection):
            try:
                cursor = connection.cursor()
                cursor.execute("CREATE DATABASE example;")
                cursor.execute("USE example;")
                cursor.execute(
                    "CREATE TABLE `testtable` (" +
                    "`id` INT NOT NULL," +
                    "`name` VARCHAR(45) NULL," +
                    "PRIMARY KEY (`id`)) " +
                    "ENGINE = MyISAM;",
                )

                cursor.execute(
                    "INSERT INTO `testtable` VALUES('42','flocker test');")
                # Note the MySQL doesn't have cursors, so PyMySQL's cursors
                # are fake. Thus we don't bother to protect this in a
                # finally block.
                cursor.close()
            finally:
                connection.close()

        getting_mysql.addCallback(add_data_node_1)

        def get_mysql_node_2(ignored):
            """
            Move MySQL to ``node_2`` and return a ``Deferred`` which fires
            with a connection to the previously created database on ``node_2``.
            """
            # Listen on different port so it's clear we're connecting to
            # newly moved container as opposed to being routed to one that
            # is about to moved:
            flocker_deploy(self, self.mysql_deployment_moved,
                           self.mysql_application_different_port)

            getting_mysql = self._get_mysql_connection(
                host=self.node_2,
                port=MYSQL_EXTERNAL_PORT + 1,
                user=user,
                passwd=MYSQL_PASSWORD,
                db=database,
            )

            return getting_mysql

        getting_mysql_2 = getting_mysql.addCallback(get_mysql_node_2)

        def verify_data_moves(connection_2):
            self.addCleanup(connection_2.close)
            cursor_2 = connection_2.cursor()
            self.addCleanup(cursor_2.close)
            cursor_2.execute("SELECT * FROM `testtable`;")
            self.assertEqual(cursor_2.fetchall(), ((42, b'flocker test'),))

        verifying_data_moves = getting_mysql_2.addCallback(verify_data_moves)
        return verifying_data_moves
