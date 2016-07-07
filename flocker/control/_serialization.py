# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Helpers for serialization and de-serialization of cluster model objects.
"""

from calendar import timegm
from collections import Set, Mapping, Iterable
from datetime import datetime
from json import dumps, loads
from uuid import UUID
from weakref import WeakKeyDictionary

from mmh3 import hash_bytes as mmh3_hash_bytes
from pyrsistent import PRecord, PVector, PMap, PSet, pmap, PClass
from pytz import UTC
from twisted.python.filepath import FilePath

from ._model import (
    Deployment, Node, DockerImage, Port, Link, RestartNever, RestartAlways,
    RestartOnFailure, Application, Dataset, Manifestation, AttachedVolume,
    NodeState, DeploymentState, NonManifestDatasets, Configuration,
    Lease, Leases, PersistentState, GenerationHash,
)
from ._diffing import _Set, _Remove, _Add, Diff


# Classes that can be serialized to disk or sent over the network:
SERIALIZABLE_CLASSES = [
    Deployment, Node, DockerImage, Port, Link, RestartNever, RestartAlways,
    RestartOnFailure, Application, Dataset, Manifestation, AttachedVolume,
    NodeState, DeploymentState, NonManifestDatasets, Configuration,
    Lease, Leases, PersistentState, GenerationHash,
    _Set, _Remove, _Add, Diff,
]

# Map of serializable class names to classes
_CONFIG_CLASS_MAP = {cls.__name__: cls for cls in SERIALIZABLE_CLASSES}

_cached_dfs_serialize_cache = WeakKeyDictionary()

_BASIC_JSON_TYPES = frozenset([str, unicode, int, long, float, bool])
_BASIC_JSON_LISTS = frozenset([list, tuple])
_BASIC_JSON_COLLECTIONS = frozenset([dict]).union(_BASIC_JSON_LISTS)

_UNCACHED_SENTINEL = object()

# Serialization marker storing the class name:
_CLASS_MARKER = u"$__class__$"


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


def to_unserialized_json(obj):
    """
    Convert a wire encodeable object into structured Python objects that
    are JSON serializable.

    :param obj: An object that can be passed to ``wire_encode``.
    :return: Python object that can be JSON serialized.
    """
    return _cached_dfs_serialize(obj)


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
