# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Persistence of cluster configuration to a SQL database.
"""
from time import sleep
from pyrsistent import PClass, field
from sqlalchemy import (
    Table, Column, LargeBinary, MetaData, create_engine, select
)
from sqlalchemy.exc import OperationalError
from twisted.internet.defer import succeed
from zope.interface import implementer

from .interface import IConfigurationStore


class NotFound(Exception):
    pass


METADATA = MetaData()
CONFIGURATION_TABLE = Table(
    "configuration",
    METADATA,
    Column("content", LargeBinary),
)


@implementer(IConfigurationStore)
class SQLConfigurationStore(PClass):
    connection_string = field(mandatory=True)

    def _connect(self):
        engine = create_engine(self.connection_string)
        while True:
            try:
                connection = engine.connect()
            except OperationalError:
                sleep(1)
            else:
                break

        return connection

    def initialize(self):
        connection = self._connect()
        table_names = set(connection.engine.table_names())
        if not set(METADATA.tables.keys()).issubset(table_names):
            METADATA.create_all(connection)
            connection.execute(
                CONFIGURATION_TABLE.insert().values(content=b"")
            )
        return succeed(None)

    def get_content(self):
        connection = self._connect()
        [result] = connection.execute(
            select([CONFIGURATION_TABLE.c.content])
        ).fetchall()
        return succeed(result['content'])

    def set_content(self, content_bytes):
        connection = self._connect()
        connection.execute(
            CONFIGURATION_TABLE.update().values(content=content_bytes)
        )
        return succeed(None)
