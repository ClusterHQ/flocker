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

from zope.interface import Interface, implementer

from ._model import SERIALIZABLE_CLASSES, Deployment, Configuration


# Serialization marker storing the class name:
_CLASS_MARKER = u"$__class__$"

# Serialization marker storing the hash of a class's field identifiers.
# The idea here is that a v2 config will use this to hash a tuple of the
# field names in a model, so that if a model has changed without the
# underlying config parser changing, or a new version created, we can
# have some tests that will start failing because the hash of fields in
# some model class no longer matches up.
_HASH_MARKER = u"$__hash__$"

# The latest configuration version. Configuration versions are
# always integers.
_CURRENT_VERSION = 1

# Map of serializable class names to classes
_CONFIG_CLASS_MAP = {cls.__name__: cls for cls in SERIALIZABLE_CLASSES}


class ConfigurationMigrationError(Exception):
    """
    Error raised when a configuration migration is unable to take place
    or complete successfully.
    """


def migrate_configuration(source_version, target_version, config):
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

    :return bytes: The updated JSON configuration after migration.
    """
    upgraded_config = config
    current_version = source_version
    for upgrade_version in range(source_version + 1, target_version + 1):
        migration_method = (
            u"configuration_v%d_v%d"
            % (current_version, upgrade_version)
        )
        try:
            migration = getattr(ConfigurationMigration, migration_method)
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
        upgraded_config = migration(config)
        current_version = current_version + 1
    return upgraded_config


class _Configuration_V1_Encoder(JSONEncoder):
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


class _Configuration_V1_Decoder(object):
    """
    JSON decoder that maps a dictionary of keys / JSON byte values to
    configuration model objects. Base decoder for version 1 configurations.
    """
    @classmethod
    def decode(cls, dictionary):
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


class IConfiguration(Interface):
    """
    An ``IConfiguration`` implementation provides a serializer and
    deserializer for a ``Configuration`` model.
    """
    def serialize(config):
        """
        Serialize the supplied configuration model to JSON.

        :param Configuration config: The configuration to serialize.
        :return bytes: The JSON representation.
        """

    def deserialize(config):
        """
        Deserialize the supplied JSON to a ``Configuration`` model.

        :param bytes config: The JSON configuration to deserialize.
        :return Configuration: The configuration model.
        """

    def encoder():
        """
        Supply an encoder that can map a series of objects to JSON.

        :return JSONEncoder encoder: A class that implements a
        ``JSONEncoder``.
        """

    def decoder():
        """
        Supply a decoder that can map a dictionary of parsed JSON
        (keys paired with byte values) to decoded model objects.

        :return function decoder: A decoding function that can be used
            as an object hook in ``json.loads``.
        """


@implementer(IConfiguration)
class Configuration_V1(object):
    """
    A version 1 configuration.
    """
    @classmethod
    def serialize(cls, config):
        # Serialized v1 configs are represented as Deployment objects,
        # not Configuration objects. This is to retain backwards
        # compatibility.
        return wire_encode(config.deployment, encoder=cls)

    @classmethod
    def deserialize(cls, config):
        return Configuration(
            version=1,
            deployment=wire_decode(config, decoder=cls)
        )

    @classmethod
    def encoder(cls):
        return _Configuration_V1_Encoder

    @classmethod
    def decoder(cls):
        return _Configuration_V1_Decoder.decode


class Configuration_V2(object):
    """
    A version 2 configuration.
    """
    @classmethod
    def serialize(cls, config):
        return wire_encode(config, encoder=cls)

    @classmethod
    def deserialize(cls, config):
        return wire_decode(config, decoder=cls)

    @classmethod
    def encoder(cls):
        """
        The encoders and decoders here may inherit and change the
        behaviour of the v1 methods.

        We may later replace the return value here with a class that
        inherits ``_Configuration_V1_Encoder`` and does something
        different in its ``default`` method, for example.

        For this design, we'll just leave them as the originals,
        since we don't need to do anything different right now.
        """
        return Configuration_V1.encoder()

    @classmethod
    def decoder(cls):
        return Configuration_V1.decoder()


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
        v1_config = Configuration_V1.deserialize(config)
        v2_config = v1_config.update(dict(version=2))
        return Configuration_V2.serialize(v2_config)


def wire_encode(obj, encoder=Configuration_V1):
    """
    Encode the given model object into bytes.

    :param obj: An object from the configuration model, e.g. ``Deployment``.
    :param class encoder: The configuration class to use when serializing.
    :return bytes: Encoded object.
    """
    return dumps(obj, cls=encoder.encoder())


def wire_decode(data, decoder=Configuration_V1):
    """
    Decode the given model object from bytes.

    :param bytes data: Encoded object.
    :param class decoder: The configuration class to use when serializing.
    """
    return loads(data, object_hook=decoder.decoder())


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
        Return the file path to a persisted configuration.
        Version 1 configurations have a version indicator as part of
        the filename. All later versions use ``current_configuration.json``
        as the filename.

        :return FilePath: The path to the service configuration file.
        """
        config_file = self._path.child(b"current_configuration.json")
        v1_config_file = self._path.child(
            b"current_configuration.v1.json")
        # For backwards compatibility, we look for a v1 named config file.
        # If we have a v1 file but no file representing a more modern config,
        # we copy the old configuration to the new file path.
        if v1_config_file.exists():
            if not config_file.exists():
                config_file.setContent(v1_config_file.getContent())
        return config_file

    def load_configuration(self):
        """
        Load the persisted configuration, upgrading the configuration format
        if an older version is detected.
        """
        self._config_path = self._versioned_config()
        config_version = 1
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
                    b"current_configuration.json")
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
