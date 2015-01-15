# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for hybridcluster/publicapi/schemas.
"""

from twisted.trial.unittest import SynchronousTestCase
from jsonschema.exceptions import ValidationError

from flocker.restapi._schema import getValidator
from flocker.volume.httpapi import SCHEMAS

def withoutItem(mapping, key):
    """
    Return a shallow copy of C{mapping} without C{key}.

    @param mapping: A copyable mapping.
    @param key: The key to exclude from the copy.
    """
    without = mapping.copy()
    del without[key]
    return without



def withItems(mapping, newValues):
    """
    Return a shallow copy of C{mapping} with new values replacing old ones.

    @param mapping: A copyable mapping.
    @param newValues: A mapping to overwrite existing values.
    """
    withAdded = mapping.copy()
    withAdded.update(newValues)
    return withAdded



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


_FAILING_NODENAMES = [
    # Not a string.
    10, {}, [], False,

    # Strings that are not IPv4 addresses.
    "hello", "1.2.3.4.5", "256.1.2.3", "-1.2.3.4", "1.2.3.4.", ".1.2.3.4",

    # Strings that are not dotted-quad formatted IPv4 addresses.
    # These are erroneously accepted.
    # https://www.pivotaltracker.com/story/show/66089428
    # "127.1", "0x7f000001", "017700000001", "2130706433",
    ]

_PASSING_NODENAMES = [
    "1.2.3.4", "255.255.255.255", "1.0.0.1",
    ]

VersionTests = buildSchemaTest(
    name="VersionTests",
    schema={'$ref': '/v1/types.json#/definitions/version'},
    failingInstances=[
        # Missing version information
        {},
        # Unexepected information
        {'revision': 'abcd', 'branch': 'asdf', 'unexepected': 5},
        # Wrong type for 'branch'
        {'revision': 'abcd', 'branch': 5},
        # Wrong type for 'revision'
        {'revision': 5, 'branch': 'asdf'},
        # 'revision' is requried
        {'branch': 'asdf'},
        # 'branch' is requried
        {'revision': 'asdf'},
    ],
    passingInstances=[
        {'revision': 'asdf', 'branch': 'asdf'},
    ],
)



VersionsTests = buildSchemaTest(
    name="VersionsTests",
    schema={'$ref': '/v1/endpoints.json#/definitions/versions'},
    failingInstances=[
        # Missing version information
        {},
        # Wrong type for SiteJuggler version
        {'SiteJuggler': []},
        # Missing 'SiteJuggler' version
        {'OtherService': {'revision':'asf', 'branch': 'asdf'}},
        # Unexpected service version has wrong type
        {
            'SiteJuggler': {'revision': 'asdf', 'branch': 'asdf'},
            'OtherService': 'not a version',
        },
    ],
    passingInstances=[
        {'SiteJuggler': {'revision': 'asdf', 'branch': 'asdf'}},
        # Unexpected services are accepted.
        {
            'SiteJuggler': {'revision': 'asdf', 'branch': 'asdf'},
            'OtherService': {'revision': 'asdf', 'branch': 'asdf'}
        },
    ],
)
