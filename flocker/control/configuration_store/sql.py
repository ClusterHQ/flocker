# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Persistence of cluster configuration to a SQL database.
"""
from .interface import IConfigurationStore

from twisted.internet.defer import succeed

from zope.interface import implementer


@implementer(IConfigurationStore)
class SQLConfigurationStore(object):
    def initialize(self):
        return succeed(None)

    def get_content(self):
        return succeed(None)

    def set_content(self, content):
        return succeed(None)
