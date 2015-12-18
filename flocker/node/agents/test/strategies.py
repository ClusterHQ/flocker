# Copyright ClusterHQ Ltd.  See LICENSE file for details.

"""
Hypothesis strategies for testing ``flocker.node.agents``.
"""

from sys import maxint

from hypothesis.strategies import (
    builds,
    integers,
    none,
    text,
    uuids,
)

from ..blockdevice import BlockDeviceVolume

blockdevice_volumes = builds(
    BlockDeviceVolume,
    blockdevice_id=text(),
    # XXX: Probably should be positive integers
    size=integers(max_value=maxint),
    attached_to=text() | none(),
    dataset_id=uuids(),
)
