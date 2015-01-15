"""
Persistence of cluster configuration.
"""

from twisted.application.service import Service
from twisted.python.filepath import FilePath

from .._config import (
    marshal_to_application_config_format, marshal_to_deployment_config_format,
    )


class ConfigurationPersistenceService(Service):
    """
    Persist configuration to disk, and load it back.

    :ivar Deployment _deployment: The current desired deployment configuration.
    """
    def __init__(self, path):
        """
        :param FilePath path: Directory where configuration files will be
            stored.
        """

    def startService(self):
        # Load application and deployment YAML files from disk, set to
        # self._deployment.
        pass

    def save(self, deployment):
        """
        Save and flush new deployment to disk.

        :return Deferred: Fires when write is finished.
        """

    def get(self):
        """
        :return Deployment: The current desired configuration.
        """
