# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Persistence of cluster configuration.
"""

from json import dumps, loads, JSONEncoder
from uuid import UUID

from eliot import Logger, write_traceback, MessageType, Field, ActionType

from pyrsistent import PRecord, PVector, PMap, PSet, pmap

from twisted.python.filepath import FilePath
from twisted.application.service import Service
from twisted.internet.defer import succeed

from ._model import SERIALIZABLE_CLASSES, Deployment


# Serialization marker storing the class name:
_CLASS_MARKER = u"$__class__$"


class _ConfigurationEncoder(JSONEncoder):
    """
    JSON encoder that can encode the configuration model.
    """
    def default(self, obj):
        if isinstance(obj, PRecord):
            result = dict(obj)
            result[_CLASS_MARKER] = obj.__class__.__name__
            return result
        elif isinstance(obj, PMap):
            return {_CLASS_MARKER: u"PMap", u"values": dict(obj).items()}
        elif isinstance(obj, (PSet, PVector, set)):
            return list(obj)
        elif isinstance(obj, FilePath):
            return {_CLASS_MARKER: u"FilePath",
                    u"path": obj.path.decode("utf-8")}
        elif isinstance(obj, UUID):
            return {_CLASS_MARKER: u"UUID",
                    "hex": unicode(obj)}
        return JSONEncoder.default(self, obj)


def wire_encode(obj):
    """
    Encode the given configuration object into bytes.

    :param obj: An object from the configuration model, e.g. ``Deployment``.
    :return bytes: Encoded object.
    """
    return dumps(obj, cls=_ConfigurationEncoder)


def wire_decode(data):
    """
    Decode the given configuration object from bytes.

    :param bytes data: Encoded object.
    :param obj: An object from the configuration model, e.g. ``Deployment``.
    """
    classes = {cls.__name__: cls for cls in SERIALIZABLE_CLASSES}

    def decode_object(dictionary):
        class_name = dictionary.get(_CLASS_MARKER, None)
        if class_name == u"FilePath":
            return FilePath(dictionary.get(u"path").encode("utf-8"))
        elif class_name == u"PMap":
            return pmap(dictionary[u"values"])
        elif class_name == u"UUID":
            return UUID(dictionary[u"hex"])
        elif class_name in classes:
            dictionary = dictionary.copy()
            dictionary.pop(_CLASS_MARKER)
            return classes[class_name].create(dictionary)
        else:
            return dictionary
    return loads(data, object_hook=decode_object)


_DEPLOYMENT_FIELD = Field(u"configuration", repr)
_LOG_STARTUP = MessageType(u"flocker-control:persistence:startup",
                           [_DEPLOYMENT_FIELD])
_LOG_SAVE = ActionType(u"flocker-control:persistence:save",
                       [_DEPLOYMENT_FIELD], [])


class ConfigurationPersistenceService(Service):
    """
    Persist configuration to disk, and load it back.

    :ivar Deployment _deployment: The current desired deployment configuration.
    """
    logger = Logger()

    def __init__(self, reactor, path):
        """
        :param reactor: Reactor to use for thread pool.
        :param FilePath path: Directory where desired deployment will be
            persisted.
        """
        self._path = path
        self._change_callbacks = []

    def startService(self):
        if not self._path.exists():
            self._path.makedirs()
        self._config_path = self._path.child(b"current_configuration.v1.json")
        if self._config_path.exists():
            self._deployment = wire_decode(
                self._config_path.getContent())
        else:
            self._deployment = Deployment(nodes=frozenset())
            self._sync_save(self._deployment)
        _LOG_STARTUP(configuration=self.get()).write(self.logger)

    def register(self, change_callback):
        """
        Register a function to be called whenever the configuration changes.

        :param change_callback: Callable that takes no arguments, will be
            called when configuration changes.
        """
        self._change_callbacks.append(change_callback)

    def _sync_save(self, deployment):
        """
        Save and flush new deployment to disk synchronously.
        """
        self._config_path.setContent(wire_encode(deployment))

    def save(self, deployment):
        """
        Save and flush new deployment to disk.

        :return Deferred: Fires when write is finished.
        """
        with _LOG_SAVE(self.logger, configuration=deployment):
            self._sync_save(deployment)
            self._deployment = deployment
            # At some future point this will likely involve talking to a
            # distributed system (e.g. ZooKeeper or etcd), so the API doesn't
            # guarantee immediate saving of the data.
            for callback in self._change_callbacks:
                try:
                    callback()
                except:
                    # Second argument will be ignored in next Eliot release, so
                    # not bothering with particular value.
                    write_traceback(self.logger, u"")
            return succeed(None)

    def get(self):
        """
        Retrieve current configuration.

        It should not be mutated.

        :return Deployment: The current desired configuration.
        """
        return self._deployment
