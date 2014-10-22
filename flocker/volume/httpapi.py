# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
A HTTP REST API for controlling the Volume Manager.
"""

from __future__ import unicode_literals

from klein import Klein

from ._schemas.v1 import V1_SCHEMAS
from ..restapi import structured


class VolumeAPIUserV1(object):
    """
    A user accessing the v1 API.
    """
    app = Klein()

    def __init__(self, volume_service):
        self.volume_service = volume_service

    @app.route("/noop")
    @structured({}, {})
    def noop(self):
        """
        Do nothing.
        """
        return None

    @app.route("/volumes", methods=["GET"])
    @structured({}, {"$ref": "/endpoints.json#/definitions/volumes/output"},
                V1_SCHEMAS)
    def volumes(self):
        d = self.volume_service.enumerate()

        def got_results(volumes):
            return {"Volumes":
                    list({"Name": volume.name.id} for volume in volumes)}
        d.addCallback(got_results)
        return d

