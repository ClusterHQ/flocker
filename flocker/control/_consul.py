# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Persistence of cluster configuration to consul.
"""
from pyrsistent import PClass, field
from treq import json_content, content
import treq
from zope.interface import implementer

from ._persistence import IConfigurationStore


CONFIG_URL = (
    "http://localhost:8500/v1/kv"
    "/com.clusterhq/flocker/current_configuration"
)


@implementer(IConfigurationStore)
class ConsulConfigurationStore(PClass):
    def get_content(self):
        d = treq.get(CONFIG_URL)
        d.addCallback(json_content)
        return d

    def set_content(self, content):
        return
