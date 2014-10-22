# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
v1 JSON Schema for volume API.
"""

from __future__ import unicode_literals


TYPES = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "definitions": {
        "volume_name": {
            "title": "Volume Name",
            "description": "The unique identifier of a volume.",
            "type": "string",
        },

        "volume": {
            "title": "Volume",
            "description": "A volume stored by the volume manager.",
            "type": "object",
            "properties": {
                "Name": dict(type={"$ref": "#/definitions/volume_name"})
            }
        }
    }
}


ENDPOINTS = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "definitions": {
        "volumes": {
            "output": {
                "type": "object",
                "properties": {
                    "Volumes": {
                        "type": "array",
                        "items": {"$ref": "/types.json#/definitions/volume"},
                    }
                },
                "additionalProperties": False,
            },
        },
    }
}


V1_SCHEMAS = {"endpoints.json": ENDPOINTS,
              "types.json": TYPES}
