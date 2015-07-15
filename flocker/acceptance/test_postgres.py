# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for running and managing PostgreSQL with Flocker.
"""
from unittest import skipUnless
from uuid import uuid4

from pyrsistent import pmap, freeze, thaw

from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase

from flocker.control import (
    Application, DockerImage, AttachedVolume, Port, Dataset, Manifestation,
    )
from flocker.testtools import loop_until

from .testtools import (require_cluster,
                        require_flocker_cli, require_moving_backend)

from ..testtools import REALISTIC_BLOCKDEVICE_SIZE


try:
    from pg8000 import connect, InterfaceError, ProgrammingError
    PG8000_INSTALLED = True
except ImportError:
    PG8000_INSTALLED = False

POSTGRES_INTERNAL_PORT = 5432
POSTGRES_EXTERNAL_PORT = 5432

POSTGRES_APPLICATION_NAME = u"postgres-volume-example"
POSTGRES_IMAGE = u"postgres"
POSTGRES_VOLUME_MOUNTPOINT = u'/var/lib/postgresql/data'


class PostgresTests(TestCase):
    """
    Tests for running and managing PostgreSQL with Flocker.
    """
    @require_flocker_cli
    @require_cluster(2)
    def setUp(self, cluster):
        """
        Deploy PostgreSQL to a node.
        """
        self.cluster = cluster

        self.node_1, self.node_2 = cluster.nodes

        new_dataset_id = unicode(uuid4())

        self.POSTGRES_APPLICATION = Application(
            name=POSTGRES_APPLICATION_NAME,
            image=DockerImage.from_string(POSTGRES_IMAGE + u':latest'),
            ports=frozenset([
                Port(internal_port=POSTGRES_INTERNAL_PORT,
                     external_port=POSTGRES_EXTERNAL_PORT),
                ]),
            volume=AttachedVolume(
                manifestation=Manifestation(
                    dataset=Dataset(
                        dataset_id=new_dataset_id,
                        metadata=pmap({"name": POSTGRES_APPLICATION_NAME}),
                        maximum_size=REALISTIC_BLOCKDEVICE_SIZE),
                    primary=True),
                mountpoint=FilePath(POSTGRES_VOLUME_MOUNTPOINT),
            ),
        )

        self.postgres_deployment = {
            u"version": 1,
            u"nodes": {
                self.node_1.reported_hostname: [POSTGRES_APPLICATION_NAME],
                self.node_2.reported_hostname: [],
            },
        }

        self.postgres_deployment_moved = {
            u"version": 1,
            u"nodes": {
                self.node_1.reported_hostname: [],
                self.node_2.reported_hostname: [POSTGRES_APPLICATION_NAME],
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
                        u"dataset_id": new_dataset_id,
                        # The location within the container where the data
                        # volume will be mounted; see:
                        # https://github.com/docker-library/postgres/blob/
                        # docker/Dockerfile.template
                        u"mountpoint": POSTGRES_VOLUME_MOUNTPOINT,
                        u"maximum_size":
                            "%d" % (REALISTIC_BLOCKDEVICE_SIZE,),
                    },
                },
            },
        }

        self.postgres_application_different_port = thaw(freeze(
            self.postgres_application).transform(
                [u"applications", POSTGRES_APPLICATION_NAME, u"ports", 0,
                 u"external"], POSTGRES_EXTERNAL_PORT + 1))

        deployed = self.cluster.flocker_deploy(
            self, self.postgres_deployment, self.postgres_application
        )
        return deployed

    def test_deploy(self):
        """
        Verify that Docker reports that PostgreSQL is running on one node and
        not another.
        """
        return self.cluster.assert_expected_deployment(self, {
            self.node_1.reported_hostname: set(
                [self.POSTGRES_APPLICATION]
            ),
            self.node_2.reported_hostname: set([]),
        })

    @require_moving_backend
    def test_moving_postgres(self):
        """
        It is possible to move PostgreSQL to a new node.
        """
        moved = self.cluster.flocker_deploy(
            self, self.postgres_deployment_moved,
            self.postgres_application
        )
        moved.addCallback(
            lambda _: self.cluster.assert_expected_deployment(self, {
                self.node_1.reported_hostname: set([]),
                self.node_2.reported_hostname: set(
                    [self.POSTGRES_APPLICATION]
                ),
            })
        )
        return moved

    def _get_postgres_connection(self, host, user, port, database=None):
        """
        Returns a ``Deferred`` which fires with a pg800 connection when one
        has been created.

        See http://pythonhosted.org//pg8000/dbapi.html#pg8000.connect for
        parameter information.
        """
        def connect_to_postgres():
            try:
                return connect(host=host, user=user, port=port,
                               database=database)
            except (InterfaceError, ProgrammingError):
                return False

        d = loop_until(connect_to_postgres)
        return d

    @skipUnless(PG8000_INSTALLED, "pg8000 not installed")
    @require_moving_backend
    def test_moving_postgres_data(self):
        """
        PostgreSQL and its data can be deployed and moved with Flocker. In
        particular, if PostgreSQL is deployed to a node, and data added to it,
        and then the application is moved to another node, the data remains
        available.
        """
        database = b'flockertest'
        user = b'postgres'

        d = self._get_postgres_connection(
            host=self.node_1.public_address,
            user=user,
            port=POSTGRES_EXTERNAL_PORT,
        )

        def create_database(connection_to_application):
            connection_to_application.autocommit = True
            application_cursor = connection_to_application.cursor()
            application_cursor.execute("CREATE DATABASE flockertest;")
            application_cursor.close()
            connection_to_application.close()

        d.addCallback(create_database)

        def connect_to_database(ignored):
            return self._get_postgres_connection(
                host=self.node_1.public_address,
                user=user,
                port=POSTGRES_EXTERNAL_PORT,
                database=database,
            )

        d.addCallback(connect_to_database)

        def add_data_node_1(db_connection_node_1):
            db_node_1_cursor = db_connection_node_1.cursor()
            db_node_1_cursor.execute(
                "CREATE TABLE testtable (testcolumn int);")
            db_node_1_cursor.execute(
                "INSERT INTO testtable (testcolumn) VALUES (3);")
            db_node_1_cursor.execute("SELECT * FROM testtable;")
            db_connection_node_1.commit()
            fetched_data = db_node_1_cursor.fetchone()[0]
            db_node_1_cursor.close()
            db_connection_node_1.close()
            self.assertEqual(fetched_data, 3)

        d.addCallback(add_data_node_1)

        def get_postgres_node_2(ignored):
            """
            Move PostgreSQL to ``node_2`` and return a ``Deferred`` which fires
            with a connection to the previously created database on ``node_2``.
            """
            d = self.cluster.flocker_deploy(
                self, self.postgres_deployment_moved,
                self.postgres_application_different_port
            )

            d.addCallback(
                lambda _: self._get_postgres_connection(
                    host=self.node_2.public_address,
                    user=user,
                    port=POSTGRES_EXTERNAL_PORT + 1,
                    database=database,
                )
            )

            return d

        d.addCallback(get_postgres_node_2)

        def verify_data_moves(db_connection_node_2):
            db_node_2_cursor = db_connection_node_2.cursor()
            db_node_2_cursor.execute("SELECT * FROM testtable;")
            fetched_data = db_node_2_cursor.fetchone()[0]
            db_node_2_cursor.close()
            db_connection_node_2.close()
            self.assertEqual(fetched_data, 3)

        d.addCallback(verify_data_moves)
        return d
