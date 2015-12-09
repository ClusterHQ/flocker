# Copyright ClusterHQ Inc.  See LICENSE file for details.

from eliot import Field, MessageType

CINDER_VOLUME = MessageType(
    u"flocker:functional:cinder:cinder_volume:created",
    [Field.for_types(
        u"id", [bytes, unicode],
        u"The Cinder-assigned unique identifier for the volume that was "
        u"created.",
    )],
)
