# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Persistence of cluster configuration to local file.
"""

from pyrsistent import PClass, field
from twisted.internet.defer import succeed
from twisted.python.filepath import FilePath
from zope.interface import implementer

from .interface import IConfigurationStore


def _process_v1_config(directory, config_path):
    """
    Check if a v1 configuration file exists and move it if necessary.
    After upgrade, the v1 configuration file is retained with an archived
    file name, which ensures the data is not lost but we do not override
    a newer configuration version next time the service starts.
    """
    v1_config_path = directory.child(b"current_configuration.v1.json")
    v1_archived_path = directory.child(b"current_configuration.v1.old.json")
    # Check for a v1 config and move to standard file location
    if v1_config_path.exists():
        v1_json = v1_config_path.getContent()
        config_path.setContent(v1_json)
        v1_config_path.moveTo(v1_archived_path)


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
        # Version 1 configurations are a special case. They do not store
        # any version information in the configuration data itself, rather they
        # can only be identified by the use of the file name
        # current_configuration.v1.json
        # Therefore we check for a version 1 configuration file and if it is
        # found, the config is upgraded, written to current_configuration.json
        # and the old file archived as current_configuration.v1.old.json
        _process_v1_config(self.directory, self.path)

    def initialize(self):
        self.initialize_sync()
        return succeed(None)

    def get_content_sync(self):
        return self.path.getContent()

    def get_content(self):
        return succeed(self.get_content_sync())

    def set_content(self, content):
        return succeed(self.path.setContent(content))
