# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Persistence of cluster configuration to a SQL database.
"""
from .interface import IConfigurationStore

from alchimia import TWISTED_STRATEGY
from alchimia.engine import TwistedEngine

from pyrsistent import PClass, field

from sqlalchemy import (
    create_engine, MetaData, Table, Column, LargeBinary
)
from sqlalchemy.schema import CreateTable

from twisted.internet.defer import inlineCallbacks, returnValue

from zope.interface import implementer

METADATA = MetaData()
CONFIGURATION_TABLE = Table(
    "configuration",
    METADATA,
    Column("content", LargeBinary),
)


@implementer(IConfigurationStore)
class SQLConfigurationStore(PClass):
    """
    An ``IConfigurationStore`` which stores content to any SQL database
    supported by SQLAlchemy.

    See: http://docs.sqlalchemy.org/en/latest/dialects/index.html
    """
    engine = field(mandatory=True, type=(TwistedEngine,))

    @classmethod
    def from_connection_string(cls, reactor, connection_string):
        engine = create_engine(
            connection_string,
            reactor=reactor,
            strategy=TWISTED_STRATEGY,
        )
        return cls(engine=engine)

    @inlineCallbacks
    def initialize(self):
        table_names = yield self.engine.table_names()
        if not set(METADATA.tables.keys()).issubset(table_names):
            yield self.engine.execute(
                CreateTable(CONFIGURATION_TABLE)
            )
            yield self.engine.execute(
                CONFIGURATION_TABLE.insert().values(content=b"")
            )
        table_names = yield self.engine.table_names()
        returnValue(None)

    @inlineCallbacks
    def get_content(self):
        result = yield self.engine.execute(
            CONFIGURATION_TABLE.select()
        )
        [content] = yield result.fetchall()
        [content] = content
        returnValue(content)

    @inlineCallbacks
    def set_content(self, content):
        yield self.engine.execute(
            CONFIGURATION_TABLE.update().values(content=content)
        )
        returnValue(None)
