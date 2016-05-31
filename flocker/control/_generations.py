# Copyright ClusterHQ Inc.  See LICENSE file for details.
# -*- test-case-name: flocker.control.test.test_generations -*-

from collections import deque
from pyrsistent import PClass, field

from ._model import GenerationHash
from ._persistence import make_generation_hash
from ._diffing import Diff, create_diff


class _GenerationRecord(PClass):
    generation_hash = field(type=GenerationHash, mandatory=True)

    # ``None`` indicates that this is the most recent record
    diff_to_next = field(type=(Diff, type(None)), mandatory=True, initial=None)


class GenerationTracker(object):

    def __init__(self, cache_size):
        self._queue = deque(maxlen=cache_size)
        self._latest_object = None
        self._latest_hash = None

    def _append_hash(self, obj_hash):
        self._latest_hash = obj_hash

    def get_diff_from_hash_to_latest(self, generation_hash, latest):
        latest_hash = make_generation_hash(latest)
        result = None

        if self._latest_latest is not None:
            new_diff = create_diff(self._latest_object, latest)
            if self._latest_hash is not None:
                self._queue.append(
                    _GenerationRecord(
                        generation_hash=self._latest_hash,
                        diff_to_next=new_diff
                    )
                )
            self._latest_object = latest
            result = new_diff

        self._append_hash(latest_hash)
        self._latest_object = latest

        return result
