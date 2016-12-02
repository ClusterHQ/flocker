# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Persistence of cluster configuration to local file.
"""

from pyrsistent import PClass, field
from twisted.internet.defer import succeed
from twisted.python.filepath import FilePath
from zope.interface import implementer

from .interface import IConfigurationStore


@implementer(IConfigurationStore)
class DirectoryConfigurationStore(PClass):
    directory = field(mandatory=True, type={FilePath})

    @property
    def path(self):
        return self.directory.child("current_configuration.json")

    def initialize_sync(self):
        if not self.directory.exists():
            self.directory.makedirs()
        if not self.path.exists():
            self.path.touch()

    def initialize(self):
        self.initialize_sync()
        return succeed(None)

    def get_content_sync(self):
        return self.path.getContent()

    def get_content(self):
        return succeed(self.get_content_sync())

    def set_content(self, content):
        return succeed(self.path.setContent(content))
