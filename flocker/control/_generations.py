# Copyright ClusterHQ Inc.  See LICENSE file for details.
# -*- test-case-name: flocker.control.test.test_generations -*-

from collections import deque
from pyrsistent import PClass, field

from ._model import GenerationHash
from ._persistence import make_generation_hash
from ._diffing import Diff, create_diff, compose_diffs


class _GenerationRecord(PClass):
    generation_hash = field(type=GenerationHash, mandatory=True)
    diff_to_next = field(type=Diff, mandatory=True)


class GenerationTracker(object):

    def __init__(self, cache_size):
        self._queue = deque(maxlen=cache_size)
        self._latest_object = None
        self._latest_hash = None

    def _append_hash(self, obj_hash):
        self._latest_hash = obj_hash

    def get_latest(self):
        return self._latest_object

    def get_latest_hash(self):
        return self._latest_hash

    def insert_latest(self, latest):
        latest_hash = make_generation_hash(latest)

        if (self._latest_object is not None and
                latest_hash != self._latest_hash):
            new_diff = create_diff(self._latest_object, latest)
            if self._latest_hash is not None:
                self._queue.append(
                    _GenerationRecord(
                        generation_hash=self._latest_hash,
                        diff_to_next=new_diff
                    )
                )

        self._latest_object = latest
        self._latest_hash = latest_hash

    def get_diff_from_hash_to_latest(self, generation_hash):
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
