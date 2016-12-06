# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Persistence of cluster configuration to a SQL database.
"""
from .interface import IConfigurationStore

from alchimia import TWISTED_STRATEGY

from pyrsistent import PClass, field

from sqlalchemy import (
    create_engine, MetaData, Table, Column, Integer, String, LargeBinary
)
from sqlalchemy.schema import CreateTable

from twisted.internet.defer import inlineCallbacks, succeed, returnValue

from zope.interface import implementer

METADATA = MetaData()
CONFIGURATION_TABLE = Table(
    "configuration",
    METADATA,
    Column("content", LargeBinary),
)


@implementer(IConfigurationStore)
class SQLConfigurationStore(PClass):

    connection_string = field(
        type=(unicode,),
        mandatory=True
    )
    reactor = field(mandatory=True)

    def _engine(self):
        return create_engine(
            self.connection_string,
            reactor=self.reactor,
            strategy=TWISTED_STRATEGY,
        )

    @inlineCallbacks
    def initialize(self):
        engine = self._engine()
        table_names = yield engine.table_names()
        if not set(METADATA.tables.keys()).issubset(table_names):
            yield engine.execute(
                CreateTable(CONFIGURATION_TABLE)
            )
            yield engine.execute(
                CONFIGURATION_TABLE.insert().values(content=b"")
            )
        table_names = yield engine.table_names()
        returnValue(None)

    @inlineCallbacks
    def get_content(self):
        engine = self._engine()
        result = yield engine.execute(
            CONFIGURATION_TABLE.select()
        )
        [content] = yield result.fetchall()
        [content] = content
        returnValue(content)

    @inlineCallbacks
    def set_content(self, content):
        engine = self._engine()
        yield engine.execute(
            CONFIGURATION_TABLE.update().values(content=content)
        )
        returnValue(None)
