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


ConfigurationTests = build_schema_test(
    name="ConfigurationTests",
    schema={'$ref': '/v1/endpoints.json#/definitions/configuration'},
    schema_store=SCHEMAS,
    failing_instances=[
        # Missing one or both keys
        {}, {"applications": {}}, {"application_deployment": {}},
    ],
    passing_instances=[
        # We don't have schema for config files yet:
        # https://clusterhq.atlassian.net/browse/FLOC-1234
        {'applications': {"x": 1},
         'application_deployment': {"y": 2}},
    ],
)
