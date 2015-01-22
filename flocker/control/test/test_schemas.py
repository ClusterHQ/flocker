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
    # failing instances
    # - wrong type for dataset_id
    # - too short string for dataset_id
    # - too long string for dataset_id
    #
    # - wrong type for metadata
    # - wrong type for key in metadata
    # - wrong type for value in metadata
    # - too-long string property name in metadata
    # - too-long string property value in metadata
    # - too many metadata properties
    #
    # - test maximum_size cases
    #
    # - missing primary
    # - wrong type for primary
    # - non-IPv4-address for primary
    )
