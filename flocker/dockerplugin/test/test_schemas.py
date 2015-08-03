# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for Docker plugin API schemas.
"""

from __future__ import unicode_literals

from ...restapi.testtools import build_schema_test
from .._api import SCHEMAS


def build_simple_test(command_name):
    """
    Build a test for simple API commands that respond only with ``Err`` field.

    :param unicode command_name: The command in the schema to validate.

    :return: ``TestCase``.
    """
    return build_schema_test(
        name=str(command_name + "Tests"),
        schema={"$ref": "/endpoints.json#/definitions/" + command_name},
        schema_store=SCHEMAS,
        failing_instances=[
            # Wrong types:
            [], "", None,
            # Missing field:
            {},
            # Wrong fields:
            {"Result": "hello"},
            # Wrong Err types:
            {"Err": 1}, {"Err": {}},
            # Extra field:
            {"Err": None, "Extra": ""},
        ],
        passing_instances=[
            {"Err": None},
            {"Err": "Something went wrong!"},
        ])

RemoveTests = build_simple_test("Remove")
UnmountTests = build_simple_test("Unmount")


PluginAttachTests = build_schema_test(
    name=str("PluginAttachTests"),
    schema={"$ref": "/endpoints.json#/definitions/PluginAttach"},
    schema_store=SCHEMAS,
    failing_instances=[
        # Wrong types:
        [], "", None,
        # Missing field:
        {},
        # Wrong fields:
        {"Result": "hello"},
        # Extra field:
        {"Implements": ["VolumeDriver"], "X": "Y"},
    ],
    passing_instances=[
        {"Implements": ["VolumeDriver"]},
    ])
