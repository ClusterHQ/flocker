# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for control API schemas.
"""

from ...restapi.testtools import build_schema_test
from ..httpapi import SCHEMAS


VersionsTests = build_schema_test(
    name="VersionsTests",
    schema={'$ref': '/v1/endpoints.json#/definitions/versions'},
    schema_store=SCHEMAS,
    failing_instances=[
        # Missing version information
        {},
        # Wrong type for Flocker version
        {'flocker': []},
        # Unexpected version.
        {
            'flocker': '0.3.0-10-dirty',
            'OtherService': '0.3.0-10-dirty',
        },
    ],
    passing_instances=[
        {'flocker': '0.3.0-10-dirty'},
    ],
)

DatasetsSchemaTests = build_schema_test(
    name="DatasetsSchemaTests",
    schema={'$ref': '/v1/endpoints.json#/definitions/datasets'},
    schema_store=SCHEMAS,
    failing_instances=[
        # wrong type for dataset_id
        {u"primary": u"10.0.0.1", u"dataset_id": 10},

        # too short string for dataset_id
        {u"primary": u"10.0.0.1", u"dataset_id": u"x" * 35},

        # too long string for dataset_id
        {u"primary": u"10.0.0.1", u"dataset_id": u"x" * 37},

        # wrong type for metadata
        {u"primary": u"10.0.0.1", u"metadata": 10},

        # wrong type for value in metadata
        {u"primary": u"10.0.0.1", u"metadata": {u"foo": 10}},

        # too-long string property name in metadata
        {u"primary": u"10.0.0.1", u"metadata": {u"x" * 257: u"10"}},

        # too-long string property value in metadata
        {u"primary": u"10.0.0.1", u"metadata": {u"foo": u"x" * 257}},

        # too many metadata properties
        {u"primary": u"10.0.0.1",
         u"metadata":
             dict.fromkeys((unicode(i) for i in range(257)), u"value")},

        # wrong type for maximum size
        {u"primary": u"10.0.0.1", u"maximum_size": u"123"},

        # too-small value for maximum size
        {u"primary": u"10.0.0.1", u"maximum_size": 123},

        # missing primary
        {u"metadata": {},
         u"maximum_size": 1024 * 1024 * 1024,
         u"dataset_id": u"x" * 36},

        # wrong type for primary
        {u"primary": 10,
         u"metadata": {},
         u"maximum_size": 1024 * 1024 * 1024,
         u"dataset_id": u"x" * 36},

        # non-IPv4-address for primary
        {u"primary": u"10.0.0.257",
         u"metadata": {},
         u"maximum_size": 1024 * 1024 * 1024,
         u"dataset_id": u"x" * 36},
        {u"primary": u"example.com",
         u"metadata": {},
         u"maximum_size": 1024 * 1024 * 1024,
         u"dataset_id": u"x" * 36},
    ],

    passing_instances=[
        # everything optional except primary
        {u"primary": u"10.0.0.1"},

        # metadata is an object with a handful of short string key/values
        {u"primary": u"10.0.0.1",
         u"metadata":
             dict.fromkeys((unicode(i) for i in range(16)), u"x" * 256)},

        # maximum_size is an integer of at least 64MiB
        {u"primary": u"10.0.0.1", u"maximum_size": 1024 * 1024 * 64},

        # dataset_id is a string of 36 characters
        {u"primary": u"10.0.0.1", u"dataset_id": u"x" * 36},

        # All of them can be combined.
        {u"primary": u"10.0.0.1",
         u"metadata":
             dict.fromkeys((unicode(i) for i in range(16)), u"x" * 256),
         u"maximum_size": 1024 * 1024 * 64,
         u"dataset_id": u"x" * 36},
    ]
)

DatasetsArrayTests = build_schema_test(
    name="DatasetsArrayTests",
    schema={'$ref': '/v1/endpoints.json#/definitions/datasets_array'},
    schema_store=SCHEMAS,
    failing_instances=[
        # Incorrect type
        {},
        # Wrong item type
        ["string"],
        # Failing dataset type (maximum_size less than minimum allowed)
        [{u"primary": u"10.0.0.1", u"maximum_size": 123}]
    ],
    passing_instances=[
        [],
        [{u"primary": u"10.0.0.1"}],
        [{u"primary": u"10.0.0.1"}, {u"primary": u"10.0.0.2"}]
    ],
)
