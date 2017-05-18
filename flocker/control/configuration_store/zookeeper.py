# Copyright (C) 2017 Nokia Corporation and/or its subsidiary(-ies). See LICENSE file for details.

"""
Persistence of cluster configuration to ZooKeeper.
"""

from contextlib import contextmanager
import datetime
import logging

from eliot import Message
from kazoo.client import KazooClient
from pyrsistent import PClass, field
from twisted.internet.defer import succeed

from zope.interface import implementer

from .interface import IConfigurationStore


ZK_CONFIG_PATH = '/flocker/configuration'

# produce Eliot logs from standard logger
class EliotLogHandler(logging.Handler):
    def emit(self, record):
        Message.new(
            message_type=u'flocker:control:store:zookeeper', message=record.getMessage()
        ).write()


logger = logging.getLogger("kazoo")
logger.setLevel(logging.INFO)
logger.addHandler(EliotLogHandler())


@implementer(IConfigurationStore)
class ZooKeeperConfigurationStore(PClass):
    zookeeper_hosts = field(mandatory=True, type=str)

    @property
    @contextmanager
    def client(self):
        _client = KazooClient(
            hosts=self.zookeeper_hosts,
            connection_retry={'max_tries': 8, 'delay': 1},
            command_retry={'max_tries': 8, 'delay': 1}
            )
        try:
            _client.start()
            yield _client
        finally:
            _client.stop()

    def initialize(self):
        with self.client as client:
            client.ensure_path(ZK_CONFIG_PATH)
        return succeed(None)

    def get_content_sync(self):
        with self.client as client:
            out, stat = client.get(ZK_CONFIG_PATH)
            mtime = datetime.datetime.fromtimestamp(stat.mtime / 1000).isoformat()
            logger.info('Fetched configuration version: %s, mtime: %s, size: %s', stat.version, mtime, len(out))
        return out

    def get_content(self):
        return succeed(self.get_content_sync())

    def set_content(self, content):
        with self.client as client:
            stat = client.set(ZK_CONFIG_PATH, content)
            mtime = datetime.datetime.fromtimestamp(stat.mtime / 1000).isoformat()
            logger.info('Stored configuration version: %s, mtime: %s, size: %s', stat.version, mtime, len(content))
        return succeed(None)


def zookeeper_store_from_options(options):
    return ZooKeeperConfigurationStore(
        zookeeper_hosts=options["zookeeper-hosts"]
    )
