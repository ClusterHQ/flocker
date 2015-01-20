# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Persistence of cluster configuration.
"""

from pickle import dumps, loads

from twisted.application.service import Service
from twisted.internet.defer import succeed

from ._model import Deployment


# These should not use Pickle!@!
# https://clusterhq.atlassian.net/browse/FLOC-1241
def serialize_deployment(deployment):
    """
    Convert a ``Deployment`` object to ``bytes``.

    :param Deployment deployment: Object to serialize.

    :return bytes: Serialized object.
    """
    return dumps(deployment)


def deserialize_deployment(data):
    """
    Create a ``Deployment`` object that was previously serialized to given
    ``bytes``.

    :param bytes data: Output of ``serialize_deployment``.

    :return Deployment: Deserialized object.
    """
    return loads(data)


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
        self._config_path = self._path.child(b"current_configuration.pickle")
        if self._config_path.exists():
            self._deployment = deserialize_deployment(
                self._config_path.getContent())
        else:
            self._deployment = Deployment(nodes=frozenset())
            self._sync_save(self._deployment)

    def _sync_save(self, deployment):
        """
        Save and flush new deployment to disk synchronously.
        """
        self._config_path.setContent(serialize_deployment(deployment))

    def save(self, deployment):
        """
        Save and flush new deployment to disk.

        :return Deferred: Fires when write is finished.
        """
        self._sync_save(deployment)
        self._deployment = deployment
        # At some future point this will likely involve talking to a
        # distributed system (e.g. ZooKeeper or etcd), so the API doesn't
        # guarantee immediate saving of the data.
        return succeed(None)

    def get(self):
        """
        Retrieve current configuration.

        It should not be mutated.

        :return Deployment: The current desired configuration.
        """
        return self._deployment
