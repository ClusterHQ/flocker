# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for interoperability between Postgres and Flocker datasets.
"""

from unittest import skipUnless

from twisted.python.filepath import FilePath

from eliot import Message

from ...testtools import loop_until
from .testtools import make_dataset_integration_testcase


try:
    from pg8000 import connect, InterfaceError, ProgrammingError
    PG8000_INSTALLED = True
except ImportError:
    PG8000_INSTALLED = False


def get_postgres_connection(host, port, database=None):
    """
    Returns a ``Deferred`` which fires with a pg8000 connection when one
    has been created.

    See http://pythonhosted.org//pg8000/dbapi.html#pg8000.connect for
    parameter information.

    :param host: Host to connect to.
    :param port: Port to connect to:
    :param database: Database to connect to.

    :return: ``Deferred`` that fires with a pg8000 connection.
    """
    def connect_to_postgres():
        try:
            return connect(host=host, user=u"postgres", port=port,
                           database=database)
        except (InterfaceError, ProgrammingError) as e:
            Message.new(
                message_type=u"acceptance:integration:postgres_connect",
                exception=unicode(e.__class__), reason=unicode(e)).write()
            return False

    d = loop_until(connect_to_postgres)
    return d


def insert_data(test_case, host, port):
    """
    Insert some data into the database.

    :param TestCase test_case: A test.
    :param host: Host to connect to.
    :param port: Port to connect to.

    :return: ``Deferred`` that fires when data has been inserted.
    """
    d = get_postgres_connection(host, port)

    def create_database(connection):
        connection.autocommit = True
        cursor = connection.cursor()
        cursor.execute("CREATE DATABASE flockertest;")
        cursor.close()
        connection.close()

    d.addCallback(create_database)

    d.addCallback(
        lambda _: get_postgres_connection(host, port, u"flockertest"))

    def add_data(connection):
        cursor = connection.cursor()
        cursor.execute(
            "CREATE TABLE testtable (testcolumn int);")
        cursor.execute(
            "INSERT INTO testtable (testcolumn) VALUES (123);")
        connection.commit()
        connection.close()
    d.addCallback(add_data)
    return d


def assert_inserted(test_case, host, port):
    """
    Verify some data has been inserted into the database.

    :param TestCase test_case: A test.
    :param host: Host to connect to.
    :param port: Port to connect to.

    :return: ``Deferred`` that fires when we verify data has been inserted.
    """
    d = get_postgres_connection(host, port, u"flockertest")

    def assert_data(connection):
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM testtable;")
        fetched_data = cursor.fetchone()[0]
        test_case.assertEqual(fetched_data, 123)
    d.addCallback(assert_data)
    return d


class PostgresIntegrationTests(make_dataset_integration_testcase(
        u"postgres", FilePath(b'/var/lib/postgresql/data'), 5432,
        insert_data, assert_inserted,
        )):
    """
    Integration tests for Postgres.
    """
    @skipUnless(PG8000_INSTALLED, "pg8000 not installed")
    def setUp(self):
        pass
