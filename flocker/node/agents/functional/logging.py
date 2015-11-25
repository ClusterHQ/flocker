# Copyright ClusterHQ Ltd.  See LICENSE file for details.

from eliot import Field, MessageType

CINDER_VOLUME = MessageType(
    u"flocker:functional:cinder:cinder_volume:created",
    [Field.for_types(
        u"volume_id", [bytes, unicode],
        u"The Cinder-assigned unique identifier for the volume that was created.",
    )],
)
