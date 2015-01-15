# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for flocker/volume/schemas.
"""

from twisted.trial.unittest import SynchronousTestCase
from jsonschema.exceptions import ValidationError

from flocker.restapi._schema import getValidator
from flocker.volume.httpapi import SCHEMAS


def buildSchemaTest(name, schema, failingInstances, passingInstances):
    """
    Create test case verifying that various instances pass and fail
    verification with a given JSON Schema.

    @param name: Name of test case to create
    @type name: L{str}

    @param schema: Schema to test
    @type schema: L{dict}
    @param failingInstances: List of instances which should fail validation
    @param passingInstances: List of instances which should pass validation

    @return The test case.
    @rtype: A L{SynchronousTestCase} subclass.
    """
    body = {
        'schema': schema,
        'validator': getValidator(schema, SCHEMAS),
        'passingInstances': passingInstances,
        'failingInstances': failingInstances,
        }
    for i, inst in enumerate(failingInstances):
        def test(self, inst=inst):
            self.assertRaises(ValidationError,
                              self.validator.validate, inst)
        test.__name__ = 'test_failsValidation_%d' % (i,)
        body[test.__name__] = test

    for i, inst in enumerate(passingInstances):
        def test(self, inst=inst):
            self.validator.validate(inst)
        test.__name__ = 'test_passesValidation_%d' % (i,)
        body[test.__name__] = test

    return type(name, (SynchronousTestCase, object), body)


VersionsTests = buildSchemaTest(
    name="VersionsTests",
    schema={'$ref': '/v1/endpoints.json#/definitions/versions'},
    failingInstances=[
        # Missing version information
        {},
        # Wrong type for SiteJuggler version
        {'flocker': []},
        # Unexpected version.
        {
            'flocker': '0.3.0-10-dirty',
            'OtherService': '0.3.0-10-dirty',
        },
    ],
    passingInstances=[
        {'flocker': '0.3.0-10-dirty'},
    ],
)
