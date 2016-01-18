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
            {"Err": 1}, {"Err": {}}, {"Err": None},
            # Extra field:
            {"Err": "", "Extra": ""},
        ],
        passing_instances=[
            {"Err": ""},
            {"Err": "Something went wrong!"},
        ])

RemoveTests = build_simple_test("Remove")
UnmountTests = build_simple_test("Unmount")
CreateTests = build_simple_test("Create")


PluginActivateTests = build_schema_test(
    name=str("PluginActivateTests"),
    schema={"$ref": "/endpoints.json#/definitions/PluginActivate"},
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


def build_path_result_tests(name):
    """
    Build a test for API commands that respond with ``Err`` and
    ``Mountpoint`` fields.

    :param unicode command_name: The command in the schema to validate.

    :return: ``TestCase``.
    """
    return build_schema_test(
        name=str(name + "Tests"),
        schema={"$ref": "/endpoints.json#/definitions/" + name},
        schema_store=SCHEMAS,
        failing_instances=[
            # Wrong types:
            [], "", None,
            # Missing field:
            {}, {"Mountpoint": "/x"},
            # Wrong fields:
            {"Result": "hello"},
            # Extra field:
            {"Err": "", "Mountpoint": "/x", "extra": "y"},
        ],
        passing_instances=[
            {"Err": "Something went wrong."},
            {"Err": "", "Mountpoint": "/x/"},
        ])

MountTests = build_path_result_tests("Mount")
PathTests = build_path_result_tests("Path")


GetTests = build_schema_test(
    name=str("GetTests"),
    schema={"$ref": "/endpoints.json#/definitions/Get"},
    schema_store=SCHEMAS,
    failing_instances=[
        # Wrong types:
        [], "", None,
        # Missing field:
        {}, {"Volume": "/x"},
        # Wrong fields:
        {"Result": "hello"},
        # Extra field:
        {"Err": "", "Volume": {"Name": "x",
                               "Mountpoint": "/y"}, "extra": "y"},
        # Missing field:
        {"Err": "", "Volume": {"Mountpoint": "/y"}},
        {"Err": "", "Volume": {"Name": "/x"}},
        # Extra field:
        {"Err": "", "Volume": {"Name": "/x",
                               "Mountpoint": "y",
                               "extra": "r"}},
    ],
    passing_instances=[
        {"Err": "Something went wrong."},
        {"Err": "", "Volume": {
            "Name": "x",
            "Mountpoint": "/x/"}},
    ])


ListTests = build_schema_test(
    name=str("GetTests"),
    schema={"$ref": "/endpoints.json#/definitions/List"},
    schema_store=SCHEMAS,
    failing_instances=[
        # Wrong types:
        [], "", None,
        # Missing field:
        {}, {"Volumes": []},
        # Wrong fields:
        {"Result": "hello"},
        # Extra field:
        {"Err": "", "Volumes": [], "extra": "y"},
        # Missing field:
        {"Err": "", "Volumes": [{"Mountpoint": "/y"}]},
        {"Err": "", "Volumes": [{"Name": "/x"}]},
        # Extra field:
        {"Err": "", "Volumes": [{"Name": "/x",
                                 "Mountpoint": "y",
                                 "extra": "r"}]},
    ],
    passing_instances=[
        {"Err": "Something went wrong."},
        {"Err": "", "Volumes": [
            {"Name": "x",
             "Mountpoint": "/x/"}]},
        {"Err": "", "Volumes": [
            {"Name": "y",
             "Mountpoint": "/y/"},
            {"Name": "x",
             "Mountpoint": "/x/"}]},
    ])
