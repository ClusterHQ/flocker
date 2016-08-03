# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Persistence of cluster configuration.
"""

from base64 import b16encode
from calendar import timegm
from datetime import datetime
from json import dumps, loads
from mmh3 import hash_bytes as mmh3_hash_bytes
from uuid import UUID
from collections import Set, Mapping, Iterable

from eliot import Logger, write_traceback, MessageType, Field, ActionType
from eliot.twisted import DeferredContext

from pyrsistent import PRecord, PVector, PMap, PSet, pmap, PClass

from pytz import UTC

from twisted.python.filepath import FilePath
from twisted.application.service import Service, MultiService
from twisted.internet.defer import succeed, maybeDeferred
from twisted.internet.task import LoopingCall

from weakref import WeakKeyDictionary

from ._model import (
    SERIALIZABLE_CLASSES, Deployment, Configuration, GenerationHash
)
from .configuration_storage.directory import DirectoryConfigurationStore

# The class at the root of the configuration tree.
ROOT_CLASS = Deployment


# Serialization marker storing the class name:
_CLASS_MARKER = u"$__class__$"

# The latest configuration version. Configuration versions are
# always integers.
_CONFIG_VERSION = 6

# Map of serializable class names to classes
_CONFIG_CLASS_MAP = {cls.__name__: cls for cls in SERIALIZABLE_CLASSES}


class ConfigurationMigrationError(Exception):
    """
    Error raised when a configuration migration is unable to
    complete successfully.
    """


class MissingMigrationError(Exception):
    """
    Error raised when a configuration migration method cannot be found.
    """
    def __init__(self, source_version, target_version):
        """
        Initialize a missing migration exception.

        :param int source_version: The version to migrate from.
        :param int target_version: The version to migrate to.
        """
        self.source_version = source_version
        self.target_version = target_version
        self.message = (
            u"Unable to find a migration path for a version {source} "
            u"to version {target} configuration. No migration method "
            u"upgrade_from_v{source} could be found.".format(
                source=self.source_version, target=self.target_version
            )
        )
        super(MissingMigrationError, self).__init__(self.message)


def migrate_configuration(source_version, target_version,
                          config, migration_class):
    """
    Migrate a persisted configuration from one version to another
    in sequential upgrades, e.g. a source version of 1 and target
    version of 3 will perform two upgrades, from version 1 to 2,
    followed by 2 to 3.

    Calls the correct ``migration_class`` class methods for
    sequential upgrades between the suppled source and target versions.

    :param int source_version: The version to migrate from.
    :param int target_version: The version to migrate to.
    :param bytes config: The source configuration blob.
    :param class migration_class: The class containing the methods
        that will be used for migration.

    :return bytes: The updated configuration blob after migration.
    :raises MissingMigrationError: Raises this exception if any of the
        required upgrade methods cannot be found in the supplied migration
        class, before attempting to execute any upgrade paths.
    """
    upgraded_config = config
    current_version = source_version
    migrations_sequence = []
    for upgrade_version in range(source_version + 1, target_version + 1):
        with _LOG_UPGRADE(configuration=upgraded_config,
                          source_version=current_version,
                          target_version=upgrade_version):
            migration_method = u"upgrade_from_v%d" % current_version
            migration = getattr(migration_class, migration_method, None)
            if migration is None:
                raise MissingMigrationError(current_version, upgrade_version)
            migrations_sequence.append(migration)
            current_version += 1
    for migration in migrations_sequence:
        upgraded_config = migration(upgraded_config)
    return upgraded_config


class ConfigurationMigration(object):
    """
    Migrate a JSON configuration from one version to another.
    """
    @classmethod
    def upgrade_from_v1(cls, config):
        """
        Migrate a v1 JSON configuration to v2.

        :param bytes config: The v1 JSON data.
        :return bytes: The v2 JSON data.
        """
        v1_config = loads(config)
        v2_config = {
            _CLASS_MARKER: u"Configuration",
            u"version": 2,
            u"deployment": v1_config
        }
        return dumps(v2_config)

    @classmethod
    def upgrade_from_v2(cls, config):
        """
        Migrate a v2 JSON configuration to v3.

        :param bytes config: The v2 JSON data.
        :return bytes: The v3 JSON data.
        """
        decoded_config = loads(config)
        decoded_config[u"version"] = 3
        decoded_config[u"deployment"][u"leases"] = {
            u"values": [], _CLASS_MARKER: u"PMap",
        }
        return dumps(decoded_config)

    @classmethod
    def upgrade_from_v3(cls, config):
        """
        Migrate a v3 JSON configuration to v4.

        :param bytes config: The v3 JSON data.
        :return bytes: The v4 JSON data.
        """
        decoded_config = loads(config)
        decoded_config[u"version"] = 4
        decoded_config[u"deployment"][u"persistent_state"] = {
            _CLASS_MARKER: u"PersistentState",
            u"blockdevice_ownership": {
                u"values": [], _CLASS_MARKER: "PMap",
            },
        }
        return dumps(decoded_config)

    @classmethod
    def upgrade_from_v4(cls, config):
        """
        Migrate a v4 JSON configuration to v5.

        :param bytes config: The v4 JSON data.
        :return bytes: The v5 JSON data.
        """
        decoded_config = loads(config)
        decoded_config[u"version"] = 5
        try:
            nodes = decoded_config[u"deployment"][u"nodes"]
        except KeyError:
            pass
        else:
            new_node_values = []
            for n in nodes:
                new_node = n
                new_node[u"applications"] = {
                    u"values": [(a[u"name"], a) for a in n[u"applications"]],
                    _CLASS_MARKER: "PMap"
                }
                new_node_values.append((new_node["uuid"], new_node))
            decoded_config[u"deployment"][u"nodes"] = {
                u"values": new_node_values,
                _CLASS_MARKER: "PMap"
            }
        return dumps(decoded_config)

    @classmethod
    def upgrade_from_v5(cls, config):
        """
        Migrate a v5 JSON configuration to v6.

        :param bytes config: The v5 JSON data.
        :return bytes: The v6 JSON data.
        """
        decoded_config = loads(config)
        decoded_config[u"version"] = 6
        try:
            nodes = decoded_config[u"deployment"][u"nodes"]
        except KeyError:
            pass
        else:
            new_node_values = []
            for node in nodes[u"values"]:
                uuid = node[0]
                applications = node[1][u"applications"][u"values"]
                for app in applications:
                    app[1].update({u'swappiness': 0})
                new_node = node[1]
                new_node[u"applications"][u"values"] = applications
                new_node_values.append((uuid, new_node))
            decoded_config[u"deployment"][u"nodes"] = {
                u"values": new_node_values,
                _CLASS_MARKER: "PMap"
            }
        return dumps(decoded_config)


def _to_serializables(obj):
    """
    This function turns assorted types into serializable objects (objects that
    can be serialized by the default JSON encoder). Note that this is done
    shallowly for containers. For example, ``PClass``es will be turned into
    dicts, but the values and keys of the dict might still not be serializable.

    It is up to higher layers to traverse containers recursively to achieve
    full serialization.

    :param obj: The object to serialize.

    :returns: An object that is shallowly JSON serializable.
    """
    if isinstance(obj, PRecord):
        result = dict(obj)
        result[_CLASS_MARKER] = obj.__class__.__name__
        return result
    elif isinstance(obj, PClass):
        result = obj._to_dict()
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
    elif isinstance(obj, datetime):
        if obj.tzinfo is None:
            raise ValueError(
                "Datetime without a timezone: {}".format(obj))
        return {_CLASS_MARKER: u"datetime",
                "seconds": timegm(obj.utctimetuple())}
    return obj


def _is_pyrsistent(obj):
    """
    Boolean check if an object is an instance of a pyrsistent object.
    """
    return isinstance(obj, (PRecord, PClass, PMap, PSet, PVector))


_BASIC_JSON_TYPES = frozenset([str, unicode, int, long, float, bool])
_BASIC_JSON_LISTS = frozenset([list, tuple])
_BASIC_JSON_COLLECTIONS = frozenset([dict]).union(_BASIC_JSON_LISTS)


_UNCACHED_SENTINEL = object()


_cached_dfs_serialize_cache = WeakKeyDictionary()


def _cached_dfs_serialize(input_object):
    """
    This serializes an input object into something that can be serialized by
    the python json encoder.

    This caches the serialization of pyrsistent objects in a
    ``WeakKeyDictionary``, so the cache should be automatically cleared when
    the input object that is cached is destroyed.

    :returns: An entirely serializable version of input_object.
    """
    # Ensure this is a quick function for basic types:
    if input_object is None:
        return None

    # Note that ``type(x) in frozenset([str, int])`` is faster than
    # ``isinstance(x, (str, int))``.
    input_type = type(input_object)
    if input_type in _BASIC_JSON_TYPES:
        return input_object

    is_pyrsistent = False
    if input_type in _BASIC_JSON_COLLECTIONS:
        # Don't send basic collections through shallow object serialization,
        # isinstance is not a very cheap operation.
        obj = input_object
    else:
        if _is_pyrsistent(input_object):
            is_pyrsistent = True
            # Using ``dict.get`` and a sentinel rather than the more pythonic
            # try/except KeyError for performance. This function is highly
            # recursive and the KeyError is guaranteed to happen the first
            # time every object is serialized. We do not want to incur the cost
            # of a caught exception for every pyrsistent object ever
            # serialized.
            cached_value = _cached_dfs_serialize_cache.get(input_object,
                                                           _UNCACHED_SENTINEL)
            if cached_value is not _UNCACHED_SENTINEL:
                return cached_value
        obj = _to_serializables(input_object)

    result = obj

    obj_type = type(obj)
    if obj_type == dict:
        result = dict((_cached_dfs_serialize(key),
                       _cached_dfs_serialize(value))
                      for key, value in obj.iteritems())
    elif obj_type == list or obj_type == tuple:
        result = list(_cached_dfs_serialize(x) for x in obj)

    if is_pyrsistent:
        _cached_dfs_serialize_cache[input_object] = result

    return result

# A couple tokens that are used below in the generation hash.
_NULLSET_TOKEN = mmh3_hash_bytes(b'NULLSET')
_MAPPING_TOKEN = mmh3_hash_bytes(b'MAPPING')
_STR_TOKEN = mmh3_hash_bytes(b'STRING')

_generation_hash_cache = WeakKeyDictionary()


def _xor_bytes(aggregating_bytearray, updating_bytes):
    """
    Aggregate bytes into a bytearray using XOR.

    This function has a somewhat particular function signature in order for it
    to be compatible with a call to `reduce`

    :param bytearray aggregating_bytearray: Resulting bytearray to aggregate
        the XOR of both input arguments byte-by-byte.

    :param bytes updating_bytes: Additional bytes to be aggregated into the
        other argument. It is assumed that this has the same size as
        aggregating_bytearray.

    :returns: aggregating_bytearray, after it has been modified by XORing all
        of the bytes in the input bytearray with ``updating_bytes``.
    """
    for i in xrange(len(aggregating_bytearray)):
        aggregating_bytearray[i] ^= ord(updating_bytes[i])
    return aggregating_bytearray


def generation_hash(input_object):
    """
    This computes the mmh3 hash for an input object, providing a consistent
    hash of deeply persistent objects across python nodes and implementations.

    :returns: An mmh3 hash of input_object.
    """
    # Ensure this is a quick function for basic types:
    # Note that ``type(x) in frozenset([str, int])`` is faster than
    # ``isinstance(x, (str, int))``.
    input_type = type(input_object)
    if (
            input_object is None or
            input_type in _BASIC_JSON_TYPES
    ):
        if input_type == unicode:
            input_type = bytes
            input_object = input_object.encode('utf8')

        if input_type == bytes:
            # Add a token to identify this as a string. This ensures that
            # strings like str('5') are hashed to different values than values
            # who have an identical JSON representation like int(5).
            object_to_process = b''.join([_STR_TOKEN, bytes(input_object)])
        else:
            # For non-string objects, just hash the JSON encoding.
            object_to_process = dumps(input_object)
        return mmh3_hash_bytes(object_to_process)

    is_pyrsistent = _is_pyrsistent(input_object)
    if is_pyrsistent:
        cached = _generation_hash_cache.get(input_object, _UNCACHED_SENTINEL)
        if cached is not _UNCACHED_SENTINEL:
            return cached

    object_to_process = input_object

    if isinstance(object_to_process, PClass):
        object_to_process = object_to_process._to_dict()

    if isinstance(object_to_process, Mapping):
        # Union a mapping token so that empty maps and empty sets have
        # different hashes.
        object_to_process = frozenset(object_to_process.iteritems()).union(
            [_MAPPING_TOKEN]
        )

    if isinstance(object_to_process, Set):
        sub_hashes = (generation_hash(x) for x in object_to_process)
        result = bytes(
            reduce(_xor_bytes, sub_hashes, bytearray(_NULLSET_TOKEN))
        )
    elif isinstance(object_to_process, Iterable):
        result = mmh3_hash_bytes(b''.join(
            generation_hash(x) for x in object_to_process
        ))
    else:
        result = mmh3_hash_bytes(wire_encode(object_to_process))

    if is_pyrsistent:
        _generation_hash_cache[input_object] = result

    return result


def make_generation_hash(x):
    """
    Creates a ``GenerationHash`` for a given argument.

    Simple helper to call ``generation_hash`` and wrap it in the
    ``GenerationHash`` ``PClass``.

    :param x: The object to hash.

    :returns: The ``GenerationHash`` for the object.
    """
    return GenerationHash(
        hash_value=generation_hash(x)
    )


def wire_encode(obj):
    """
    Encode the given model object into bytes.

    :param obj: An object from the configuration model, e.g. ``Deployment``.
    :return bytes: Encoded object.
    """
    return dumps(_cached_dfs_serialize(obj))


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
        elif class_name == u"datetime":
            return datetime.fromtimestamp(dictionary[u"seconds"], UTC)
        elif class_name in _CONFIG_CLASS_MAP:
            dictionary = dictionary.copy()
            dictionary.pop(_CLASS_MARKER)
            return _CONFIG_CLASS_MAP[class_name].create(dictionary)
        else:
            return dictionary

    return loads(data, object_hook=decode)


def to_unserialized_json(obj):
    """
    Convert a wire encodeable object into structured Python objects that
    are JSON serializable.

    :param obj: An object that can be passed to ``wire_encode``.
    :return: Python object that can be JSON serialized.
    """
    return _cached_dfs_serialize(obj)

_DEPLOYMENT_FIELD = Field(u"configuration", to_unserialized_json)
_LOG_STARTUP = MessageType(u"flocker-control:persistence:startup",
                           [_DEPLOYMENT_FIELD])
_LOG_SAVE = ActionType(u"flocker-control:persistence:save",
                       [_DEPLOYMENT_FIELD], [])

_UPGRADE_SOURCE_FIELD = Field.for_types(
    u"source_version", [int], u"Configuration version to upgrade from.")
_UPGRADE_TARGET_FIELD = Field.for_types(
    u"target_version", [int], u"Configuration version to upgrade to.")
_LOG_UPGRADE = ActionType(u"flocker-control:persistence:migrate_configuration",
                          [_DEPLOYMENT_FIELD, _UPGRADE_SOURCE_FIELD,
                           _UPGRADE_TARGET_FIELD, ], [])
_LOG_EXPIRE = MessageType(
    u"flocker-control:persistence:lease-expired",
    [Field(u"dataset_id", unicode), Field(u"node_id", unicode)],
    u"A lease for a dataset has expired.")

_LOG_UNCHANGED_DEPLOYMENT_NOT_SAVED = MessageType(
    u"flocker-control:persistence:unchanged-deployment-not-saved",
    [],
    u"The persistence service was told to save a deployment which is the same "
    u"as the already-saved deployment.  It has optimized this away."
)


class LeaseService(Service):
    """
    Manage leases.
    In particular, clear out expired leases once a second.

    :ivar _reactor: A ``IReactorTime`` provider.
    :ivar _persistence_service: The persistence service to act with.
    :ivar _lc: A ``twisted.internet.task.LoopingCall`` run every second
        to update the configured leases by releasing leases that have
        expired.
    """
    def __init__(self, reactor, persistence_service):
        self._reactor = reactor
        self._persistence_service = persistence_service

    def startService(self):
        self._lc = LoopingCall(self._expire)
        self._lc.clock = self._reactor
        self._lc.start(1)

    def stopService(self):
        self._lc.stop()

    def _expire(self):
        now = datetime.fromtimestamp(self._reactor.seconds(), tz=UTC)

        def expire(leases):
            updated_leases = leases.expire(now)
            for dataset_id in set(leases) - set(updated_leases):
                _LOG_EXPIRE(dataset_id=dataset_id,
                            node_id=leases[dataset_id].node_id).write()
            return updated_leases
        return update_leases(expire, self._persistence_service)


def update_leases(transform, persistence_service):
    """
    Update the leases configuration in the persistence service.

    :param transform: A function to execute on the currently configured
        leases to manipulate their state.
    :param persistence_service: The persistence service to which the
        updated configuration will be saved.

    :return Deferred: Fires with the new ``Leases`` instance when the
        persistence service has saved.
    """
    config = persistence_service.get()
    # XXX This is an optimization to avoid calling ``set`` unless the
    # value has changed. ``set`` is slow.
    new_leases = transform(config.leases)
    if new_leases != config.leases:
        # The leases in the configuration are out of date.
        new_config = config.set("leases", new_leases)
        d = persistence_service.save(new_config)
        d.addCallback(lambda _: new_config.leases)
        return d
    return succeed(new_leases)


def load_and_upgrade(config_json):
    config_dict = loads(config_json)
    config_version = config_dict.get('version', 1)
    if config_version < _CONFIG_VERSION:
        with _LOG_UPGRADE(configuration=config_json,
                          source_version=config_version,
                          target_version=_CONFIG_VERSION):
            config_json = migrate_configuration(
                config_version, _CONFIG_VERSION,
                config_json, ConfigurationMigration)
    config = wire_decode(config_json)
    return config.deployment


class ConfigurationPersistenceService(MultiService):
    """
    Persist configuration to disk, and load it back.

    :ivar Deployment _deployment: The current desired deployment configuration.
    :ivar bytes _hash: A SHA256 hash of the configuration.
    """
    logger = Logger()
    _deployment = None
    _hash = None

    def __init__(self, reactor, configuration_saver=None,
                 initial_deployment=None):
        """
        :param reactor: Reactor to use for thread pool.
        """
        MultiService.__init__(self)
        if configuration_saver is None:
            configuration_saver = lambda deployment_data: None
        self._configuration_save = configuration_saver
        self._change_callbacks = []
        if initial_deployment is None:
            initial_deployment = Deployment()
        initial_deployment_data = self._encode_deployment(initial_deployment)
        self._hash = self._hash_deployment_data(initial_deployment_data)
        self._deployment = initial_deployment
        LeaseService(reactor, self).setServiceParent(self)

    def startService(self):
        # Register the flocker-control service on this node
        # curl -X PUT
        # -d '{"Name": "flocker-control",
        #      "Check": {"tcp": "localhost:4523",
        #                "interval": "10s", "timeout": "1s"}}'
        # http://localhost:8500/v1/agent/service/register
        MultiService.startService(self)
        _LOG_STARTUP(configuration=self.get()).write()

    def configuration_hash(self):
        """
        :return bytes: A hash of the configuration.
        """
        return self._hash

    @classmethod
    def from_json_bytes(cls, reactor, json_bytes, configuration_saver):
        if json_bytes:
            initial_deployment = load_and_upgrade(json_bytes)
        else:
            initial_deployment = None

        return cls(
            reactor=reactor,
            configuration_saver=configuration_saver,
            initial_deployment=initial_deployment,
        )

    @classmethod
    def from_configuration_store(cls, reactor, configuration_store):
        """
        Load the persisted configuration, upgrading the configuration format
        if an older version is detected.
        """
        d = configuration_store.initialize()
        d.addCallback(lambda ignored: configuration_store.get_content())

        def load(json_bytes):
            return cls.from_json_bytes(
                reactor=reactor,
                json_bytes=json_bytes,
                configuration_saver=configuration_store.set_content,
            )
        d.addCallback(load)
        return d

    @classmethod
    def from_directory(cls, reactor, directory):
        configuration_store = DirectoryConfigurationStore(
            directory=directory
        )
        configuration_store.initialize_sync()
        return cls.from_json_bytes(
            reactor=reactor,
            json_bytes=configuration_store.get_content_sync(),
            configuration_saver=configuration_store.set_content,
        )

    def register(self, change_callback):
        """
        Register a function to be called whenever the configuration changes.

        :param change_callback: Callable that takes no arguments, will be
            called when configuration changes.
        """
        self._change_callbacks.append(change_callback)

    def _encode_deployment(self, deployment):
        config = Configuration(
            version=_CONFIG_VERSION,
            deployment=deployment
        )
        return wire_encode(config)

    def _hash_deployment_data(self, deployment_data):
        return b16encode(mmh3_hash_bytes(deployment_data)).lower()

    def save(self, deployment):
        """
        Save and flush new deployment to disk.

        :return Deferred: Fires when write is finished.
        """
        if deployment == self._deployment:
            _LOG_UNCHANGED_DEPLOYMENT_NOT_SAVED().write()
            return succeed(None)

        def finish(ignored):
            # At some future point this will likely involve talking to a
            # distributed system (e.g. ZooKeeper or etcd), so the API doesn't
            # guarantee immediate saving of the data.
            for callback in self._change_callbacks:
                try:
                    callback()
                except:
                    # Second argument will be ignored in next Eliot release, so
                    # not bothering with particular value.
                    write_traceback()
            return succeed(None)

        with _LOG_SAVE(configuration=deployment) as action:
            deployment_data = self._encode_deployment(deployment)
            self._hash = self._hash_deployment_data(deployment_data)
            self._deployment = deployment
            d = maybeDeferred(
                self._configuration_save,
                deployment_data
            )

            with action.context():
                d = DeferredContext(d)
                d.addCallback(finish)
                d.addActionFinish()
        return d.result

    def get(self):
        """
        Retrieve current configuration.

        It should not be mutated.

        :return Deployment: The current desired configuration.
        """
        return self._deployment
