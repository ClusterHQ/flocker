# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
Tests for ``flocker.restapi._schema``.
"""

import copy

from jsonschema.exceptions import RefResolutionError, ValidationError

from .._schema import (
    LocalRefResolver, SchemaNotProvided, getValidator, resolveSchema)
from ...testtools import TestCase


class LocalResolverTests(TestCase):
    """
    Tests for L{LocalRefResolver}.
    """

    def test_resolveRemoteRaises(self):
        """
        L{LocalRefResolver.resolve_remote} raises an exception.
        """
        resolver = LocalRefResolver(base_uri=b'', referrer={})
        self.assertRaises(SchemaNotProvided,
                          resolver.resolve_remote,
                          b'bad://nothing.invalid/schema')

    def test_resolvingRaisesError(self):
        """
        The L{LocalRefResolver.resolving} context manager raises an exception
        when entered.
        """
        resolver = LocalRefResolver(base_uri=b'', referrer={})
        context = resolver.resolving(b'http://json-schema.org/schema')
        e = self.assertRaises(RefResolutionError, context.__enter__)

        self.assertIsInstance(e.args[0], SchemaNotProvided)


class GetValidatorTests(TestCase):
    """
    Tests for L{getValidator}.
    """

    def test_basic(self):
        """
        L{getValidator} returns an L{jsonschema} validator.

        In particular, it has C{.validate} and C{.iter_items} methods.
        """
        validator = getValidator({u'type': u'string'}, {})
        validator.validate('abc')
        self.assertEqual(len(list(validator.iter_errors({}))), 1)
        self.assertRaises(ValidationError, validator.validate, {})

    def test_resolver(self):
        """
        L{getValidator} returns an L{jsonschema} validator that uses
        the given schema store to lookup references.
        """
        validator = getValidator({u'$ref': u'schema.json'},
                                 {'schema.json': {'type': 'string'}})
        self.assertRaises(ValidationError, validator.validate, {})


class ResolveSchemaTests(TestCase):
    """
    Tests for L{ResolveSchema}.
    """
    STORE = {b"/path/types.json":
             {"absolute": {"$ref": "/path/types.json#/actual"},
              "relative": {"$ref": "types.json#/actual"},
              "local": {"$ref": "#/actual"},
              "list": {"list": [1, 2, {"$ref": "#/actual"}]},
              "nested": {"key": {"$ref": "#/actual"}, "key2": 3},
              "nested_additional": {"key": {"$ref": "#/actual",
                                            "another": 3,
                                            "additional":
                                            {"$ref": "#/actual"}}},
              "extra_nested": {"key": {"key2": {"$ref": "#/actual"}}},
              "actual": {"hello": "there"}},
             b"/path/endpoints.json":
             {"type": {"$ref": "types.json#/local"}}}

    def test_resolvedHasDraftVersion(self):
        """
        The returned schema has the I{$schema} key with draft 4 indicated.
        """
        result = resolveSchema({}, {})
        self.assertEqual(
            result,
            {"$schema": "http://json-schema.org/draft-04/schema#"})

    def test_nestedDictionaries(self):
        """
        References within nested dictionaries are resolved.
        """
        schema = {"$ref": "/path/types.json#/nested"}
        result = resolveSchema(schema, self.STORE)
        self.assertEqual(result,
                         {"$schema": "http://json-schema.org/draft-04/schema#",
                          "key": {"hello": "there"}, "key2": 3})

    def test_extraNestedDictionaries(self):
        """
        References within extra nested dictionaries are resolved.
        """
        schema = {"$ref": "/path/types.json#/extra_nested"}
        result = resolveSchema(schema, self.STORE)
        self.assertEqual(result,
                         {"$schema": "http://json-schema.org/draft-04/schema#",
                          "key": {"key2": {"hello": "there"}}})

    def test_keysNotPreserved(self):
        """
        Keys in the same dictionary as the C{"$ref"} are not preserved when
        reference resolving is done.
        """
        schema = {"$ref": "/path/types.json#/nested_additional"}
        result = resolveSchema(schema, self.STORE)
        self.assertEqual(result,
                         {"$schema": "http://json-schema.org/draft-04/schema#",
                          "key": {"hello": "there"}})

    def test_lists(self):
        """
        References within lists are resolved.
        """
        schema = {"$ref": "/path/types.json#/list"}
        result = resolveSchema(schema, self.STORE)
        self.assertEqual(result,
                         {"$schema": "http://json-schema.org/draft-04/schema#",
                          "list": [1, 2, {"hello": "there"}]})

    def test_recursive(self):
        """
        References within separate documents referenced in the input schema are
        resolved.
        """
        schema = {"$ref": "/path/endpoints.json#/type"}
        result = resolveSchema(schema, self.STORE)
        self.assertEqual(result,
                         {"$schema": "http://json-schema.org/draft-04/schema#",
                          "hello": "there"})

    def test_absoluteInReference(self):
        """
        Absolute references within a separate document referenced in the input
        schema are resolved with reference to the separate document.
        """
        schema = {"$ref": "/path/types.json#/absolute"}
        result = resolveSchema(schema, self.STORE)
        self.assertEqual(result,
                         {"$schema": "http://json-schema.org/draft-04/schema#",
                          "hello": "there"})

    def test_relativeInReference(self):
        """
        Relative references within a separate document referenced in the input
        schema are resolved with reference to the separate document.
        """
        schema = {"$ref": "/path/types.json#/relative"}
        result = resolveSchema(schema, self.STORE)
        self.assertEqual(result,
                         {"$schema": "http://json-schema.org/draft-04/schema#",
                          "hello": "there"})

    def test_localInReference(self):
        """
        Local references within a separate document referenced in the input
        schema are resolved with reference to the separate document.
        """
        schema = {"$ref": "/path/types.json#/local",
                  # Make sure reference doesn't end up here:
                  "actual": {"something": "else"}}
        result = resolveSchema(schema, self.STORE)
        self.assertEqual(result,
                         {"$schema": "http://json-schema.org/draft-04/schema#",
                          "hello": "there"})

    def test_inputUnmodified(self):
        """
        The input object is not modified by resolution.
        """
        schema = {"hello": {"$ref": "/path/types.json#/nested_additional"}}
        original = copy.deepcopy(schema)
        resolveSchema(schema, self.STORE)
        self.assertEqual(schema, original)

    def test_storeUnmodified(self):
        """
        The store is not modified by resolution.
        """
        schema = {"hello": {"$ref": "/path/types.json#/nested_additional"}}
        original = copy.deepcopy(self.STORE)
        resolveSchema(schema, self.STORE)
        self.assertEqual(self.STORE, original)
