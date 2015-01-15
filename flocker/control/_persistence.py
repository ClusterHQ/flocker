# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Persistence of cluster configuration.
"""

from json import dumps, loads

from twisted.application.service import Service

from ._config import (
    marshal_to_application_config_format, marshal_to_deployment_config_format,
    deployment_from_configuration_files
    )
from ._model import Deployment


class ConfigurationPersistenceService(Service):
    """
    Persist configuration to disk, and load it back.

    :ivar Deployment _deployment: The current desired deployment configuration.
    """
    def __init__(self, reactor, path):
        """
        :param reactor: Reactor to use for thread pool.
        :param FilePath path: Directory where desired deployment will be
            persisted.
        """
        self._path = path

    def startService(self):
        if not self._path.exists():
            self._path.makedirs()
        self._config_path = self._path.child(b"current_configuration.json")
        if self._config_path.exists():
            data = loads(self._config_path.getContent())
            self._deployment = deployment_from_configuration_files(
                data[u"applications"], data[u"deployment"])
        else:
            self._deployment = Deployment(nodes=frozenset())

    def save(self, deployment):
        """
        Save and flush new deployment to disk.

        :return Deferred: Fires when write is finished.
        """
        data = {
            u"applications": marshal_to_application_config_format(deployment),
            u"deployment": marshal_to_deployment_config_format(deployment),
            }
        self._config_path.setContent(dumps(data))
        self._deployment = deployment
        from twisted.internet.defer import succeed
        return succeed(None)

    def get(self):
        """
        :return Deployment: The current desired configuration.
        """
        return self._deployment

