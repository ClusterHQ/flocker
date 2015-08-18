# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Persistence of cluster configuration.
"""

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

from ._model import SERIALIZABLE_CLASSES, Deployment, Configuration

# The class at the root of the configuration tree.
ROOT_CLASS = Deployment


# Serialization marker storing the class name:
_CLASS_MARKER = u"$__class__$"

# The latest configuration version. Configuration versions are
# always integers.
_CONFIG_VERSION = 2

# Map of serializable class names to classes
_CONFIG_CLASS_MAP = {cls.__name__: cls for cls in SERIALIZABLE_CLASSES}


class ConfigurationMigrationError(Exception):
    """
    Error raised when a configuration migration is unable to take place
    or complete successfully.
    """


def migrate_configuration(source_version, target_version,
                          config, migration_class):
    """
    Migrate a persisted configuration from one version to another
    in sequential upgrades, e.g. a source version of 1 and target
    version of 3 will perform two upgrades, from version 1 to 2,
    followed by 2 to 3.

    Calls the correct ``ConfigurationMigration`` class methods for
    the suppled source and target versions.

    :param int source_version: The version to migrate from.
    :param int target_version: The version to migrate to.
    :param bytes config: The JSON-encoded source configuration.
    :param class migration_class: The class containing the methods
        that will be used for migration.

    :return bytes: The updated JSON configuration after migration.
    """
    upgraded_config = config
    current_version = source_version
    for upgrade_version in range(source_version + 1, target_version + 1):
        with _LOG_UPGRADE(configuration=upgraded_config,
                          source_version=current_version,
                          target_version=upgrade_version):
            migration_method = (
                u"configuration_v%d_v%d"
                % (current_version, upgrade_version)
            )
            try:
                migration = getattr(migration_class, migration_method)
            except AttributeError:
                message = (
                    u"Unable to find a migration path for a version " +
                    unicode(source_version) + u" to version " +
                    unicode(target_version) + u" configuration. " +
                    u"No migration method exists for v" +
                    unicode(current_version) + u" to v" +
                    unicode(upgrade_version) + u"."
                )
                raise ConfigurationMigrationError(message)
            upgraded_config = migration(upgraded_config)
            current_version = current_version + 1
    return upgraded_config


class ConfigurationMigration(object):
    """
    Migrate a JSON configuration from one version to another.
    """
    @classmethod
    def configuration_v1_v2(cls, config):
        """
        Migrate a v1 JSON configuration to v2.

        :param bytes config: The v1 JSON data.
        :return bytes: The v2 JSON data.
        """
        v2_config = Configuration(
            version=2, deployment=wire_decode(config))
        return wire_encode(v2_config)


class _Configuration_Encoder(JSONEncoder):
    """
    JSON encoder that can encode the configuration model.
    Base encoder for version 1 configurations.
    """
    def default(self, obj):
        if isinstance(obj, PRecord):
            result = dict(obj)
            result[_CLASS_MARKER] = obj.__class__.__name__
            return result
        elif isinstance(obj, PMap):
            return {
                _CLASS_MARKER: u"PMap", u"values": dict(obj).items()
            }
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
    Encode the given model object into bytes.

    :param obj: An object from the configuration model, e.g. ``Deployment``.
    :return bytes: Encoded object.
    """
    return dumps(obj, cls=_Configuration_Encoder)


def wire_decode(data):
    """
    Decode the given model object from bytes.

    :param bytes data: Encoded object.
    """
    def decode(dictionary):
        class_name = dictionary.get(_CLASS_MARKER, None)
        if class_name == u"FilePath":
            return FilePath(dictionary.get(u"path").encode("utf-8"))
        elif class_name == u"PMap":
            return pmap(dictionary[u"values"])
        elif class_name == u"UUID":
            return UUID(dictionary[u"hex"])
        elif class_name in _CONFIG_CLASS_MAP:
            dictionary = dictionary.copy()
            dictionary.pop(_CLASS_MARKER)
            return _CONFIG_CLASS_MAP[class_name].create(dictionary)
        else:
            return dictionary

    return loads(data, object_hook=decode)


_DEPLOYMENT_FIELD = Field(u"configuration", repr)
_LOG_STARTUP = MessageType(u"flocker-control:persistence:startup",
                           [_DEPLOYMENT_FIELD])
_LOG_SAVE = ActionType(u"flocker-control:persistence:save",
                       [_DEPLOYMENT_FIELD], [])
_LOG_UPGRADE = ActionType(u"flocker-control:persistence:migrate_configuration",
                          [_DEPLOYMENT_FIELD,
                           Field(u"source_version", repr),
                           Field(u"target_version", repr)], [])


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

    def load_configuration(self):
        """
        Load the persisted configuration, upgrading the configuration format
        if an older version is detected.
        """
        self._config_path = self._path.child(b"current_configuration.json")
        v1_config_path = self._path.child(
            b"current_configuration.v1.json")
        # Check for a v1 config and upgrade to latest if found.
        if v1_config_path.exists():
            if not self._config_path.exists():
                v1_json = v1_config_path.getContent()
                with _LOG_UPGRADE(self.logger,
                                  configuration=v1_json,
                                  source_version=1,
                                  target_version=_CONFIG_VERSION):
                    updated_json = migrate_configuration(
                        1, _CONFIG_VERSION, v1_json,
                        ConfigurationMigration)
                    self._config_path.setContent(updated_json)
        if self._config_path.exists():
            config_json = self._config_path.getContent()
            config_dict = loads(config_json)
            if 'version' in config_dict:
                config_version = config_dict['version']
            else:
                config_version = 1
            if config_version < _CONFIG_VERSION:
                with _LOG_UPGRADE(self.logger,
                                  configuration=config_json,
                                  source_version=config_version,
                                  target_version=_CONFIG_VERSION):
                    config_json = migrate_configuration(
                        config_version, _CONFIG_VERSION,
                        config_json, ConfigurationMigration)
            config = wire_decode(config_json)
            self._deployment = config.deployment
            self._sync_save(config.deployment)
        else:
            self._deployment = Deployment.create_empty()
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
        Save and flush new configuration to disk synchronously.
        """
        config = Configuration(version=_CONFIG_VERSION, deployment=deployment)
        self._config_path.setContent(wire_encode(config))

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
