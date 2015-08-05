# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Persistence of cluster configuration.
"""

import sys

from json import dumps, loads, JSONEncoder
from uuid import UUID

from datetime import datetime

from eliot import Logger, write_traceback, MessageType, Field, ActionType

from pyrsistent import PRecord, PVector, PMap, PSet, pmap

from pytz import UTC

from twisted.python.filepath import FilePath
from twisted.application.service import Service, MultiService
from twisted.internet import reactor as default_reactor
from twisted.internet.defer import succeed
from twisted.internet.task import LoopingCall

from zope.interface import Interface, implementer

from ._model import SERIALIZABLE_CLASSES, Deployment


# Serialization marker storing the class name:
_CLASS_MARKER = u"$__class__$"

# The latest configuration version. Configuration versions are
# always integers.
_CURRENT_VERSION = 1

# Formatted bytes representing a versioned config file name.
_VERSIONED_CONFIG_FILE = b"current_configuration.v%d.json"

# Map of serializable class names to classes
_CONFIG_CLASS_MAP = {cls.__name__: cls for cls in SERIALIZABLE_CLASSES}


def migrate_configuration(source_version, target_version, config):
    """
    Instantiates the applicable configuration migration class for two
    versions of a persisted configuration and performs a migration.

    :param int source_version: The version to migrate from.
    :param int target_version: The version to migrate to.
    :param bytes config: The JSON-encoded source configuration.

    :return bytes: The updated JSON configuration after migration.
    """
    migration = (
        u"_ConfigurationMigration_V%d_V%d"
        % tuple(sorted([source_version, target_version]))
    )
    migration_class = getattr(sys.modules[__name__], migration)
    config_dict = loads(config)
    if source_version < target_version:
        result = migration_class.up(config_dict)
    else:
        result = migration_class.down(config_dict)
    return dumps(result)


class _IConfigurationMigration(Interface):
    """
    A ConfigurationMigration class provides an interface to migrate between
    two different versions of a persisted cluster configuration.

    A ConfigurationMigration class must follow a particular naming
    convention of ``_ConfigurationMigration_Vx_Vy`` where x and y represent
    the pre and post migration version numbers. This is because the persistence
    service, upon start, performs automatic sequential upgrades from the most
    recent configuration format detected on storage to the latest version
    available and looks for the required migration classes according to
    this convention.

    Example: a class to migrate between version 1 and 2 configuration formats
    will be called ``_ConfigurationMigration_V1_V2``.
    """
    def up(configuration):
        """
        Migrate a Vx source configuration dict to a Vy target
        configuration format and return the updated dictionary.

        :param dict configuration: The Vx configuration.
        """

    def down(configuration):
        """
        Migrate a Vy source configuration dict to a Vx target
        configuration format and return the updated dictionary.

        :param dict configuration: The Vy configuration.
        """


@implementer(_IConfigurationMigration)
class _ConfigurationMigration_V0_V1(object):
    """
    Migrate between v0 and v1 configurations.
    v1 adds the ``nodes`` key to a ``Deployment`` configuration.
    """
    @classmethod
    def up(cls, configuration):
        configuration[u"nodes"] = []
        return configuration

    @classmethod
    def down(cls, configuration):
        configuration.pop(u"nodes")
        return configuration


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
    classes = _CONFIG_CLASS_MAP

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
    loaded = loads(data, object_hook=decode_object)
    return loaded


_DEPLOYMENT_FIELD = Field(u"configuration", repr)
_LOG_STARTUP = MessageType(u"flocker-control:persistence:startup",
                           [_DEPLOYMENT_FIELD])
_LOG_SAVE = ActionType(u"flocker-control:persistence:save",
                       [_DEPLOYMENT_FIELD], [])


class LeaseService(Service):
    """
    Manage leases.
    In particular, clear out expired leases once a second.

    :ivar _reactor: A ``twisted.internet.reactor`` implementation.
    :ivar _persistence_service: The persistence service to act with.
    :ivar _lc: A ``twisted.internet.task.LoopingCall`` run every second
        to update the configured leases by releasing leases that have
        expired.
    """
    def __init__(self, reactor, persistence_service):
        if reactor is None:
            reactor = default_reactor
        self._reactor = reactor
        self._persistence_service = persistence_service

    def startService(self):
        self._lc = LoopingCall(self._expire)
        self._lc.clock = self._reactor
        self._lc.start(1)

    def stopService(self):
        self._lc.stop()

    def _expire(self):
        now = datetime.now(tz=UTC)
        return update_leases(lambda leases: leases.expire(now),
                             self._persistence_service)


def update_leases(transform, persistence_service):
    """
    Update the leases configuration in the persistence service.

    :param transform: A function to execute on the currently configured
        leases to manipulate their state.
    :param persistence_service: The persistence service to which the
        updated configuration will be saved.

    :return Deferred: Fires when the persistence service has saved.
    """
    # XXX we cannot manipulate leases in this branch since the configuration
    # doesn't know anything about them yet. See FLOC-2735.
    # So instead we do nothing for now.
    return succeed(None)


class ConfigurationPersistenceService(MultiService):
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
        MultiService.__init__(self)
        self._path = path
        self._change_callbacks = []
        LeaseService(reactor, self).setServiceParent(self)

    def startService(self):
        if not self._path.exists():
            self._path.makedirs()
        self.load_configuration()
        MultiService.startService(self)
        _LOG_STARTUP(configuration=self.get()).write(self.logger)

    def _versioned_config(self):
        """
        Sequentially and decrementally check for versioned configuration
        files, from the current version to version 1. Return the file
        found along with its version number, or if no valid
        configuration file exists, return the current version number
        and the expected file path of a configuration file matching
        the latest version.

        :return: A ``tuple`` comprising a version ``int`` and
            config ``FilePath``.
        """
        config_files = [
            (
                version,
                self._path.child(_VERSIONED_CONFIG_FILE % version)
            )
            for version in range(_CURRENT_VERSION, -1, -1)
        ]
        # Check for each possible versioned config file, from newest
        # to oldest and return the first match.
        for version, config_file in config_files:
            if config_file.exists():
                return (version, config_file)
        return (
            _CURRENT_VERSION,
            self._path.child(_VERSIONED_CONFIG_FILE % _CURRENT_VERSION)
        )

    def load_configuration(self):
        """
        Load the persisted configuration, upgrading the configuration format
        if an older version is detected.
        """
        config_version, self._config_path = self._versioned_config()
        if config_version < _CURRENT_VERSION:
            current_config = self._config_path.getContent()
            required_upgrades = range(
                config_version + 1, _CURRENT_VERSION + 1)
            for new_version in required_upgrades:
                current_config = migrate_configuration(
                    config_version, new_version, current_config
                )
                config_version = new_version
                self._config_path = self._path.child(
                    _VERSIONED_CONFIG_FILE % new_version)
            self._deployment = wire_decode(current_config)
            self._sync_save(self._deployment)
        elif self._config_path.exists():
            self._deployment = wire_decode(
                self._config_path.getContent())
        else:
            self._deployment = Deployment(nodes=frozenset())
            self._sync_save(self._deployment)

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
