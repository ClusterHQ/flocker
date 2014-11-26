# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for running and managing PostgreSQL with Flocker.
"""
from unittest import skipUnless

from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase

from flocker.node._model import Application, DockerImage, AttachedVolume, Port
from flocker.testtools import loop_until

from .testtools import (assert_expected_deployment, flocker_deploy, get_nodes,
                        require_flocker_cli)

try:
    from psycopg2 import connect, OperationalError
    PSYCOPG2_INSTALLED = True
except ImportError:
    PSYCOPG2_INSTALLED = False

POSTGRES_INTERNAL_PORT = 5432
POSTGRES_EXTERNAL_PORT = 5432

POSTGRES_APPLICATION_NAME = u"postgres-volume-example"
POSTGRES_IMAGE = u"postgres"
POSTGRES_VOLUME_MOUNTPOINT = u'/var/lib/postgresql/data'

POSTGRES_APPLICATION = Application(
    name=POSTGRES_APPLICATION_NAME,
    image=DockerImage.from_string(POSTGRES_IMAGE + u':latest'),
    ports=frozenset([
        Port(internal_port=POSTGRES_INTERNAL_PORT,
             external_port=POSTGRES_EXTERNAL_PORT),
        ]),
    volume=AttachedVolume(
        name=POSTGRES_APPLICATION_NAME,
        mountpoint=FilePath(POSTGRES_VOLUME_MOUNTPOINT),
    ),
)


class PostgresTests(TestCase):
    """
    Tests for running and managing PostgreSQL with Flocker.

    Similar to:
    http://doc-dev.clusterhq.com/gettingstarted/examples/postgres.html

    # TODO (Note for submission)
    # If this is suitable, I will add the new dependencies (currently just the
    # latest https://pypi.python.org/pypi/psycopg2) to setup.py. Each
    # dependency must also go in the internal documentation for packages used.
    #
    # This uses psycopg2 which requires, on OS X for example
    # ``brew install postgresql``. Perhaps it would be better to use
    # http://python.projects.pgfoundry.org, a pure Python implementation. If
    # not, should this just document that you need to install PostgreSQL?.

    http://python.projects.pgfoundry.org/docs/1.1/
    """
    @require_flocker_cli
    def setUp(self):
        """
        Deploy PostgreSQL to a node.
        """
        getting_nodes = get_nodes(self, num_nodes=2)

        def deploy_postgres(node_ips):
            self.node_1, self.node_2 = node_ips

            postgres_deployment = {
                u"version": 1,
                u"nodes": {
                    self.node_1: [POSTGRES_APPLICATION_NAME],
                    self.node_2: [],
                },
            }

            self.postgres_deployment_moved = {
                u"version": 1,
                u"nodes": {
                    self.node_1: [],
                    self.node_2: [POSTGRES_APPLICATION_NAME],
                },
            }

            self.postgres_application = {
                u"version": 1,
                u"applications": {
                    POSTGRES_APPLICATION_NAME: {
                        u"image": POSTGRES_IMAGE,
                        u"ports": [{
                            u"internal": POSTGRES_INTERNAL_PORT,
                            u"external": POSTGRES_EXTERNAL_PORT,
                        }],
                        u"volume": {
                            # The location within the container where the data
                            # volume will be mounted; see:
                            # https://github.com/docker-library/postgres/blob/
                            # docker/Dockerfile.template
                            u"mountpoint": POSTGRES_VOLUME_MOUNTPOINT,
                        },
                    },
                },
            }

            flocker_deploy(self, postgres_deployment,
                           self.postgres_application)

        getting_nodes.addCallback(deploy_postgres)
        return getting_nodes

    def test_deploy(self):
        """
        Verify that Docker reports that PostgreSQL is running on one node and
        not another.
        """
        d = assert_expected_deployment(self, {
            self.node_1: set([POSTGRES_APPLICATION]),
            self.node_2: set([]),
        })

        return d

    def test_moving_postgres(self):
        """
        It is possible to move PostgreSQL to a new node.
        """
        flocker_deploy(self, self.postgres_deployment_moved,
                       self.postgres_application)

        asserting_postgres_moved = assert_expected_deployment(self, {
            self.node_1: set([]),
            self.node_2: set([POSTGRES_APPLICATION]),
        })

        return asserting_postgres_moved

    def _get_postgres_connection(self, host, user, port, database=None):
        """
        Returns a ``Deferred`` which fires with a psycopg2 connection when one
        has been created.

        See http://pythonhosted.org//psycopg2/module.html#psycopg2.connect for
        parameter information.
        """
        def connect_to_postgres():
            try:
                return connect(host=host, user=user, port=port,
                               database=database)
            except OperationalError:
                return False

        d = loop_until(connect_to_postgres)
        return d

    @skipUnless(PSYCOPG2_INSTALLED, "Psycopg2 not installed")
    def test_moving_postgres_data(self):
        """
        PostgreSQL and its data can be deployed and moved with Flocker. In
        particular, if PostgreSQL is deployed to a node, and data added to it,
        and then the application is moved to another node, the data remains
        available.
        """
        # SQL injection is not a real concern here, and it seems impossible
        # to pass some these variables via psycopg2 so string concatenation
        # is used.
        database = b'flockertest'
        table = b'testtable'
        user = b'postgres'
        column = b'testcolumn'
        data = 3

        connecting_to_application = self._get_postgres_connection(
            host=self.node_1, user=user, port=POSTGRES_EXTERNAL_PORT)

        def create_database(connection_to_application):
            connection_to_application.autocommit = True
            with connection_to_application.cursor() as application_cursor:
                application_cursor.execute("CREATE DATABASE " + database + ";")

        connecting_to_application.addCallback(create_database)

        def connect_to_database(ignored):
            getting_postgres = self._get_postgres_connection(
                host=self.node_1,
                user=user,
                port=POSTGRES_EXTERNAL_PORT,
                database=database,
            )

            return getting_postgres

        connecting_to_database = connecting_to_application.addCallback(
            connect_to_database)

        def add_data_node_1(connection_to_db):
            with connection_to_db as db_connection_node_1:
                with db_connection_node_1.cursor() as db_node_1_cursor:
                    db_node_1_cursor.execute(
                        "CREATE TABLE " + table + " (" + column + " int);")
                    db_node_1_cursor.execute(
                        "INSERT INTO " + table + " (" + column +
                        ") VALUES (%(data)s);", {'data': data})
                    db_node_1_cursor.execute("SELECT * FROM " + table + ";")
                    db_connection_node_1.commit()
                    self.assertEqual(db_node_1_cursor.fetchone()[0], data)

        connecting_to_database.addCallback(add_data_node_1)

        def get_postgres_node_2(ignored):
            """
            Move PostgreSQL to ``node_2`` and return a ``Deferred`` which fires
            with a connection to the previously created database on ``node_2``.
            """
            flocker_deploy(self, self.postgres_deployment_moved,
                           self.postgres_application)

            getting_postgres = self._get_postgres_connection(
                host=self.node_2,
                user=user,
                port=POSTGRES_EXTERNAL_PORT,
                database=database,
            )

            return getting_postgres

        getting_postgres_2 = connecting_to_database.addCallback(
            get_postgres_node_2)

        def verify_data_moves(connection_2):
            with connection_2 as db_connection_node_2:
                with db_connection_node_2.cursor() as db_node_2_cursor:
                    db_node_2_cursor.execute("SELECT * FROM " + table + ";")
                    self.assertEqual(db_node_2_cursor.fetchone()[0], data)

        verifying_data_moves = getting_postgres_2.addCallback(
            verify_data_moves)
        return verifying_data_moves
