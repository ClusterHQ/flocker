# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for flocker/volume/schemas.
"""

from twisted.trial.unittest import SynchronousTestCase
from jsonschema.exceptions import ValidationError

from flocker.restapi._schema import getValidator
from flocker.volume.httpapi import SCHEMAS


def build_schema_test(name, schema, failing_instances, passing_instances):
    """
    Create test case verifying that various instances pass and fail
    verification with a given JSON Schema.

    :param bytes name: Name of test case to create.
    :param dict schema: Schema to test.
    :param list failing_instances: List of instances which should fail
        validation.
    :param list passing_instances: List of instances which should pass
        validation.

    :returns: The test case; a ``SynchronousTestCase} subclass.
    """
    body = {
        'schema': schema,
        'validator': getValidator(schema, SCHEMAS),
        'passingInstances': passing_instances,
        'failingInstances': failing_instances,
        }
    for i, inst in enumerate(failing_instances):
        def test(self, inst=inst):
            self.assertRaises(ValidationError,
                              self.validator.validate, inst)
        test.__name__ = 'test_fails_validation_%d' % (i,)
        body[test.__name__] = test

    for i, inst in enumerate(passing_instances):
        def test(self, inst=inst):
            self.validator.validate(inst)
        test.__name__ = 'test_passes_validation_%d' % (i,)
        body[test.__name__] = test

    return type(name, (SynchronousTestCase, object), body)


VersionsTests = build_schema_test(
    name="VersionsTests",
    schema={'$ref': '/v1/endpoints.json#/definitions/versions'},
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
