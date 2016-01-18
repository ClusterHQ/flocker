# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Helpers for validating API input and output against JSON Schema.

See https://python-jsonschema.readthedocs.org/en/v2.3.0/.
"""

import copy

from jsonschema.validators import RefResolver, validator_for
from jsonschema import draft4_format_checker

__all__ = [
    "SchemaNotProvided",
    "LocalRefResolver",
    "getValidator",
    "resolveSchema",
]


class SchemaNotProvided(Exception):
    """
    Tried to reference a schema that wasn't predefined.
    """


class LocalRefResolver(RefResolver):
    """
    A L{RefResolver} that doesn't try to resolve remote schema.
    """
    def resolve_remote(self, uri):
        raise SchemaNotProvided(uri)


def getValidator(schema, schema_store):
    """
    Get a L{jsonschema} validator for C{schema}.

    @param schema: The JSON Schema to validate against.
    @type schema: L{dict}

    @param dict schema_store: A mapping between schema paths
        (e.g. ``b/v1/types.json``) and the JSON schema structure.
    """
    # The base_uri here isn't correct for the schema,
    # but does give proper relative paths.
    resolver = LocalRefResolver(
        base_uri=b'',
        referrer=schema, store=schema_store)
    resolver.resolution_scope = b''
    return validator_for(schema)(
        schema, resolver=resolver, format_checker=draft4_format_checker)


def resolveSchema(schema, schemaStore):
    """
    Recursively resolve all I{$ref} JSON references in a JSON Schema.

    @param schema: A L{dict} with a JSON Schema.

    @param schemaStore: A L{dict} mapping file paths to JSON Schema loaded
        as L{dict}.

    @return: The resolved JSON Schema.
    @rtype: L{dict}
    """
    result = copy.deepcopy(schema)
    resolver = LocalRefResolver(base_uri=b'', referrer=schema,
                                store=schemaStore)

    def resolve(obj):
        if isinstance(obj, list):
            for item in obj:
                resolve(item)
            return

        if isinstance(obj, dict):
            if "$ref" in obj:
                with resolver.resolving(obj[u'$ref']) as resolved:
                    resolve(resolved)
                    obj.clear()
                    obj.update(resolved)
            else:
                for value in obj.values():
                    resolve(value)

    resolve(result)
    result["$schema"] = "http://json-schema.org/draft-04/schema#"
    return result
