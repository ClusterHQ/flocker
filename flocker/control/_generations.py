# Copyright ClusterHQ Inc.  See LICENSE file for details.
# -*- test-case-name: flocker.control.test.test_generations -*-

"""
Module for classes that assist in tracking generations of objects and applying
diffs to change objects from one generation to another.
"""

from collections import deque
from pyrsistent import PClass, field

from ._model import GenerationHash
from ._persistence import make_generation_hash
from ._diffing import Diff, create_diff, compose_diffs


class _GenerationRecord(PClass):
    """
    Helper object that stores a specific generation of an object and a Diff to
    the next object.

    :ivar GenerationHash generation_hash: The generation hash of the expected
        input object.

    :ivar Diff diff_to_next: The diff to convert an object with generation
        ``generation_hash`` into an object with a hash equivalent to the next
        ``GenerationHash`` in the queue.
    """
    generation_hash = field(type=GenerationHash, mandatory=True)
    diff_to_next = field(type=Diff, mandatory=True)


class GenerationTracker(object):
    """
    An object used to track the latest version of an object, and a queue of the
    previous generations of the object, including diffs to convert former
    objects to the latest version of the object.

    This lets you quickly look up a diff to convert an object X from generation
    hash H to the latest version of the object.

    :ivar _queue: A queue of ``_GenerationRecord`` s describing a series of
        ``Diff`` s to convert objects from a specific hash to the latest
        version.
    :ivar _latest_object: The most recent version of the object being tracked.
    :ivar _latest_hash: The most recent hash of the object being tracked.
    """

    def __init__(self, cache_size):
        """
        Construct a ``GenerationTracker``

        :param cache_size: The number of previous revisions to store in the
            queue. ``Diff`` s from versions of the object before ``cache_size``
            changes ago are dropped.
        """
        self._queue = deque(maxlen=cache_size)
        self._latest_object = None
        self._latest_hash = None

    def insert_latest(self, latest):
        """
        Insert a new version of the object to be the object.

        If the object is different than what is currently thought to be the
        latest version of the object, this will add an additional
        ``_GenerationRecord`` to the queue (and drop one if the queue is full).
        """
        if latest == self._latest_object:
            return
        latest_hash = make_generation_hash(latest)

        if (self._latest_object is not None and
                latest_hash != self._latest_hash):
            new_diff = create_diff(self._latest_object, latest)
            self._queue.append(
                _GenerationRecord(
                    generation_hash=self._latest_hash,
                    diff_to_next=new_diff
                )
            )

        self._latest_object = latest
        self._latest_hash = latest_hash

    def get_diff_from_hash_to_latest(self, generation_hash):
        """
        Compute and return the diff from a previous version of the object to
        the latest version of the object.

        :param generation_hash: The generation hash of the previous version of
            the object.

        :returns: A `Diff` that will convert a former version of the object
            being tracked. Or ``None`` if this object is no longer tracking any
            previous version object with the passed in ``generation_hash``.
        """
        if self._latest_hash == generation_hash:
            return compose_diffs([])

        results = []
        for record in self._queue:
            if record.generation_hash == generation_hash:
                results = [record.diff_to_next]
            elif results:
                results.append(record.diff_to_next)

        if results:
            return compose_diffs(results)
        else:
            return None
