# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for control API schemas.
"""

from uuid import uuid4

from ...restapi.testtools import build_schema_test
from ..httpapi import SCHEMAS


# The validator that detects a validity problem
INVALID_NUMERIC_NOT_MULTIPLE_OF = 'multipleOf'
INVALID_NUMERIC_TOO_HIGH = 'maximum'
INVALID_NUMERIC_TOO_LOW = 'minimum'
INVALID_STRING_TOO_LONG = 'maxLength'
INVALID_STRING_PATTERN = 'pattern'
INVALID_ARRAY_ITEMS_MAXIMUM = 'maxItems'
INVALID_ARRAY_ITEMS_NOT_UNIQUE = 'uniqueItems'
INVALID_OBJECT_PROPERTY_MISSING = 'required'
INVALID_OBJECT_PROPERTY_UNDEFINED = 'additionalProperties'
INVALID_OBJECT_PROPERTIES_MAXIMUM = 'maxProperties'
INVALID_OBJECT_NO_MATCH = 'oneOf'
INVALID_WRONG_TYPE = 'type'

valid_uuid = unicode(uuid4())

# The following two UUIDs are invalid, but are of the correct
# length and loose format for a UUID. They will be caught out
# by the regex in the schema types definition.
# This UUID has a 3 at the start of the 3rd block, which is
# not valid for UUIDv4 format.
bad_uuid_1 = u'75a15c23-8dd6-3f29-8164-6d60928bf3cc'
# This UUID has a 'P' in the 2nd block, which is not valid
# for UUIDv4 format.
bad_uuid_2 = u'75a15c23-8dP6-4f29-8164-6d60928bf3cc'

VersionsTests = build_schema_test(
    name="VersionsTests",
    schema={'$ref': '/v1/endpoints.json#/definitions/versions'},
    schema_store=SCHEMAS,
    failing_instances={
        INVALID_OBJECT_PROPERTY_UNDEFINED: [
            # Unexpected version.
            {
                'flocker': '0.3.0-10-dirty',
                'OtherService': '0.3.0-10-dirty',
            },
        ],
        INVALID_OBJECT_PROPERTY_MISSING: [
            # Missing version information
            {},
        ],
        INVALID_WRONG_TYPE: [
            # Wrong type for Flocker version
            {'flocker': []},
        ],
    },
    passing_instances=[
        {'flocker': '0.3.0-10-dirty'},
    ],
)


ConfigurationContainersUpdateSchemaTests = build_schema_test(
    name="ConfigurationContainersUpdateSchemaTests",
    schema={
        '$ref':
            '/v1/endpoints.json#/definitions/configuration_container_update'
    },
    schema_store=SCHEMAS,
    failing_instances={
        INVALID_OBJECT_PROPERTY_UNDEFINED: [
            # Extra properties
            {u'node_uuid': valid_uuid, u'image': u'nginx:latest'},
        ],
        INVALID_STRING_PATTERN: [
            # Node UUID not a uuid
            {u'node_uuid': u'idonotexist'},
        ],
        INVALID_OBJECT_PROPERTY_MISSING: [
            # Host missing
            {},
        ],
        INVALID_WRONG_TYPE: [
            # node_uuid wrong type
            {u'node_uuid': 1},
        ],
    },
    passing_instances=[
        {u'node_uuid': valid_uuid},
    ],
)


ConfigurationContainersSchemaTests = build_schema_test(
    name="ConfigurationContainersSchemaTests",
    schema={'$ref': '/v1/endpoints.json#/definitions/configuration_container'},
    schema_store=SCHEMAS,
    failing_instances={
        INVALID_OBJECT_PROPERTY_UNDEFINED: [
            # Volume with extra field
            {
                'node_uuid': valid_uuid,
                'image': 'postgres',
                'name': 'postgres',
                'volumes': [{'dataset_id': "x" * 36,
                             'mountpoint': '/var/db',
                             'extra': 'value'}],
            },
            # Ports given but invalid key present
            {
                'node_uuid': valid_uuid,
                'image': 'postgres',
                'name': 'postgres',
                'ports': [{'container': 80, 'external': '1'}]
            },
            # Environment given with empty name
            {
                'node_uuid': valid_uuid,
                'image': 'postgres',
                'name': 'postgres',
                'environment': {
                    'POSTGRES_USER': 'admin',
                    '': 9.4
                }
            },
        ],
        INVALID_NUMERIC_TOO_HIGH: [
            # Links given but local port is greater than max (65535)
            {
                'node_uuid': valid_uuid,
                'image': 'nginx:latest',
                'name': 'webserver',
                'links': [{
                    'alias': 'postgres',
                    'local_port': 65536,
                    'remote_port': 54320
                }]
            },
            # Links given but remote port is greater than max (65535)
            {
                'node_uuid': valid_uuid,
                'image': 'nginx:latest',
                'name': 'webserver',
                'links': [{
                    'alias': 'postgres',
                    'local_port': 5432,
                    'remote_port': 65536
                }]
            },
            # CPU shares given but greater than max
            {
                'node_uuid': valid_uuid,
                'image': 'postgres',
                'name': 'postgres',
                'cpu_shares': 1025
            },
        ],
        INVALID_ARRAY_ITEMS_MAXIMUM: [
            # More than one volume (this will eventually work - see FLOC-49)
            {
                'node_uuid': valid_uuid,
                'image': 'postgres',
                'name': 'postgres',
                'volumes': [{'dataset_id': "x" * 36,
                             'mountpoint': '/var/db'},
                            {'dataset_id': "y" * 36,
                             'mountpoint': '/var/db2'}],
            },
        ],
        INVALID_NUMERIC_TOO_LOW: [
            # CPU shares given but negative
            {
                'node_uuid': valid_uuid,
                'image': 'postgres',
                'name': 'postgres',
                'cpu_shares': -512
            },
            # Memory limit given but negative
            {
                'node_uuid': valid_uuid,
                'image': 'postgres',
                'name': 'postgres',
                'memory_limit': -1024
            },
        ],
        INVALID_OBJECT_NO_MATCH: [
            # None of the schemas under oneOf match, so all errors are oneOf
            # Restart policy given but not a string
            {
                'node_uuid': valid_uuid,
                'image': 'postgres',
                'name': 'postgres',
                'restart_policy': 1
            },
            # Restart policy string given but not an allowed value
            {
                'node_uuid': valid_uuid,
                'image': 'postgres',
                'name': 'postgres',
                'restart_policy': {"name": "no restart"}
            },
            # Restart policy is on-failure but max retry count is negative
            {
                'node_uuid': valid_uuid,
                'image': 'postgres',
                'name': 'postgres',
                'restart_policy': {
                    "name": "on-failure", "maximum_retry_count": -1
                }
            },
            # Restart policy is on-failure but max retry count is NaN
            {
                'node_uuid': valid_uuid,
                'image': 'postgres',
                'name': 'postgres',
                'restart_policy': {
                    "name": "on-failure", "maximum_retry_count": "15"
                }
            },
            # Restart policy has max retry count but no name
            {
                'node_uuid': valid_uuid,
                'image': 'postgres',
                'name': 'postgres',
                'restart_policy': {
                    "maximum_retry_count": 15
                }
            },
        ],
        INVALID_STRING_PATTERN: [
            # node_uuid not UUID format
            {
                'node_uuid': 'idonotexist',
                'image': 'clusterhq/redis',
                'name': 'my_container'
            },
            # node_uuid not a valid v4 UUID
            {
                'node_uuid': bad_uuid_1,
                'image': 'clusterhq/redis',
                'name': 'my_container'
            },
            # node_uuid not a valid hex UUID
            {
                'node_uuid': bad_uuid_2,
                'image': 'clusterhq/redis',
                'name': 'my_container'
            },
            # Name not valid
            {
                'node_uuid': valid_uuid,
                'image': 'clusterhq/redis',
                'name': '@*!'
            },
            # Links given but alias has hyphen
            {
                'node_uuid': valid_uuid,
                'image': 'nginx:latest',
                'name': 'webserver',
                'links': [{
                    'alias': 'xxx-yyy',
                    'local_port': 5432,
                    'remote_port': 54320
                }]
            },
            # Links given but alias has underscore
            {
                'node_uuid': valid_uuid,
                'image': 'nginx:latest',
                'name': 'webserver',
                'links': [{
                    'alias': 'xxx_yyy',
                    'local_port': 5432,
                    'remote_port': 54320
                }]
            },
            # Path doesn't start with /
            {
                'node_uuid': valid_uuid,
                'image': 'postgres',
                'name': 'postgres',
                'volumes': [{'dataset_id': valid_uuid,
                             'mountpoint': 'var/db2'}],
            },
        ],
        INVALID_OBJECT_PROPERTY_MISSING: [
            # Name missing
            {'node_uuid': valid_uuid, 'image': 'clusterhq/redis'},
            # node_uuid missing
            {'image': 'clusterhq/redis', 'name': 'my_container'},
            # Image missing
            {'node_uuid': valid_uuid, 'name': 'my_container'},
            # Links given but alias missing
            {
                'node_uuid': valid_uuid,
                'image': 'nginx:latest',
                'name': 'webserver',
                'links': [{
                    'local_port': 5432,
                    'remote_port': 54320
                }]
            },
            # Links given but local port missing
            {
                'node_uuid': valid_uuid,
                'image': 'nginx:latest',
                'name': 'webserver',
                'links': [{
                    'alias': 'postgres',
                    'remote_port': 54320
                }]
            },
            # Links given but remote port missing
            {
                'node_uuid': valid_uuid,
                'image': 'nginx:latest',
                'name': 'webserver',
                'links': [{
                    'alias': 'postgres',
                    'local_port': 5432,
                }]
            },
            # Volume missing dataset_id
            {
                'node_uuid': valid_uuid,
                'image': 'postgres',
                'name': 'postgres',
                'volumes': [{'mountpoint': '/var/db'}],
            },
            # Volume missing mountpoint
            {
                'node_uuid': valid_uuid,
                'image': 'postgres',
                'name': 'postgres',
                'volumes': [{'dataset_id': valid_uuid}],
            },
        ],
        INVALID_WRONG_TYPE: [
            # node_uuid wrong type
            {
                'node_uuid': 1,
                'image': 'clusterhq/redis',
                'name': 'my_container'
            },
            # Name wrong type
            {'node_uuid': valid_uuid, 'image': 'clusterhq/redis', 'name': 1},
            # Image wrong type
            {'node_uuid': valid_uuid, 'image': 1, 'name': 'my_container'},
            # Ports given but not a list of mappings
            {
                'node_uuid': valid_uuid,
                'image': 'postgres',
                'name': 'postgres',
                'ports': 'I am not a list of port maps'
            },
            # Ports given but internal is not valid
            {
                'node_uuid': valid_uuid,
                'image': 'postgres',
                'name': 'postgres',
                'ports': [{'internal': 'xxx', 'external': 8080}]
            },
            # Ports given but external is not valid
            {
                'node_uuid': valid_uuid,
                'image': 'postgres',
                'name': 'postgres',
                'ports': [{'internal': 80, 'external': '1'}]
            },
            # Ports given but external is not valid integer
            {
                'node_uuid': valid_uuid,
                'image': 'postgres',
                'name': 'postgres',
                'ports': [{'internal': 80, 'external': 22.5}]
            },
            # Environment given but not a dict
            {
                'node_uuid': valid_uuid,
                'image': 'postgres',
                'name': 'postgres',
                'environment': 'x=y'
            },
            # Environment given but at least one entry is not a string
            {
                'node_uuid': valid_uuid,
                'image': 'postgres',
                'name': 'postgres',
                'environment': {
                    'POSTGRES_USER': 'admin',
                    'POSTGRES_VERSION': 9.4
                }
            },
            # CPU shares given but not an integer
            {
                'node_uuid': valid_uuid,
                'image': 'postgres',
                'name': 'postgres',
                'cpu_shares': '512'
            },
            # Memory limit given but not an integer
            {
                'node_uuid': valid_uuid,
                'image': 'postgres',
                'name': 'postgres',
                'memory_limit': '250MB'
            },
            # Links given but not a list
            {
                'node_uuid': valid_uuid,
                'image': 'nginx:latest',
                'name': 'webserver',
                'links': {
                    'alias': 'postgres',
                    'local_port': 5432,
                    'remote_port': 54320
                }
            },
            # Links given but alias is not a string
            {
                'node_uuid': valid_uuid,
                'image': 'nginx:latest',
                'name': 'webserver',
                'links': [{
                    'alias': {"name": "postgres"},
                    'local_port': 5432,
                    'remote_port': 54320
                }]
            },
            # Links given but local port is not an integer
            {
                'node_uuid': valid_uuid,
                'image': 'nginx:latest',
                'name': 'webserver',
                'links': [{
                    'alias': 'postgres',
                    'local_port': '5432',
                    'remote_port': 54320
                }]
            },
            # Links given but remote port is not an integer
            {
                'node_uuid': valid_uuid,
                'image': 'nginx:latest',
                'name': 'webserver',
                'links': [{
                    'alias': 'postgres',
                    'local_port': 5432,
                    'remote_port': '54320'
                }]
            },
            # Volume with dataset_id of wrong type
            {
                'node_uuid': valid_uuid,
                'image': 'postgres',
                'name': 'postgres',
                'volumes': [{'dataset_id': 123,
                             'mountpoint': '/var/db'}],
            },
            # Volume with mountpoint of wrong type
            {
                'node_uuid': valid_uuid,
                'image': 'postgres',
                'name': 'postgres',
                'volumes': [{'dataset_id': valid_uuid,
                             'mountpoint': 123}],
            },
            # Command line must be array
            {
                'node_uuid': valid_uuid,
                'image': 'postgres',
                'name': 'postgres',
                'command_line': 'xx'
            },
            # Command line must be array of strings
            {
                'node_uuid': valid_uuid,
                'image': 'postgres',
                'name': 'postgres',
                'command_line': ['xx', 123]
            }
        ],
        INVALID_ARRAY_ITEMS_NOT_UNIQUE: [
            # Ports given but not unique
            {
                'node_uuid': valid_uuid,
                'image': 'postgres',
                'name': 'postgres',
                'ports': [
                    {'internal': 80, 'external': 8080},
                    {'internal': 80, 'external': 8080},
                ]
            },
        ],
    },
    passing_instances=[
        {
            'node_uuid': valid_uuid,
            'image': 'postgres',
            'name': 'postgres'
        },
        {
            'node_uuid': valid_uuid,
            'image': 'postgres',
            'name': '/postgres-8.1_server'
        },
        {
            'node_uuid': valid_uuid,
            'image': 'docker/postgres',
            'name': 'postgres'
        },
        {
            'node_uuid': valid_uuid,
            'image': 'docker/postgres:latest',
            'name': 'postgres'
        },
        {
            'node_uuid': valid_uuid,
            'image': 'postgres',
            'name': 'postgres',
            'ports': [{'internal': 80, 'external': 8080}]
        },
        {
            'node_uuid': valid_uuid,
            'image': 'postgres',
            'name': 'postgres',
            'ports': [
                {'internal': 80, 'external': 8080},
                {'internal': 3306, 'external': 42000}
            ]
        },
        {
            'node_uuid': valid_uuid,
            'image': 'postgres',
            'name': 'postgres',
            'environment': {
                'POSTGRES_USER': 'admin',
                'POSTGRES_VERSION': '9.4'
            }
        },
        {
            'node_uuid': valid_uuid,
            'image': 'docker/postgres:latest',
            'name': 'postgres',
            'restart_policy': {'name': 'never'}
        },
        {
            'node_uuid': valid_uuid,
            'image': 'docker/postgres:latest',
            'name': 'postgres',
            'restart_policy': {'name': 'always'}
        },
        {
            'node_uuid': valid_uuid,
            'image': 'docker/postgres:latest',
            'name': 'postgres',
            'restart_policy': {'name': 'on-failure'}
        },
        {
            'node_uuid': valid_uuid,
            'image': 'docker/postgres:latest',
            'name': 'postgres',
            'restart_policy': {
                'name': 'on-failure', 'maximum_retry_count': 5
            }
        },
        {
            'node_uuid': valid_uuid,
            'image': 'docker/postgres:latest',
            'name': 'postgres',
            'cpu_shares': 512
        },
        {
            'node_uuid': valid_uuid,
            'image': 'docker/postgres:latest',
            'name': 'postgres',
            'memory_limit': 262144000
        },
        {
            'node_uuid': valid_uuid,
            'image': 'nginx:latest',
            'name': 'webserver',
            'links': [{
                'alias': 'postgres',
                'local_port': 5432,
                'remote_port': 54320
            }]
        },
        {
            'node_uuid': valid_uuid,
            'image': 'postgres',
            'name': 'postgres',
            'volumes': [{'dataset_id': valid_uuid,
                         'mountpoint': '/var/db'}],
        },
        {
            'node_uuid': valid_uuid,
            'image': 'postgres',
            'name': 'postgres',
            'volumes': [],
        },
        {
            'node_uuid': valid_uuid,
            'image': 'postgres',
            'name': 'postgres',
            'command_line': ['ls', '/data'],
        },
    ],
)

CONFIGURATION_DATASETS_FAILING_INSTANCES = {
    INVALID_OBJECT_PROPERTY_UNDEFINED: [
        # too-long string property name in metadata
        {u"primary": valid_uuid, u"metadata": {u"x" * 257: u"10"}},
    ],
    INVALID_OBJECT_PROPERTIES_MAXIMUM: [
        # too many metadata properties
        {u"primary": valid_uuid,
         u"metadata":
             dict.fromkeys((unicode(i) for i in range(257)), u"value")},
    ],
    INVALID_STRING_TOO_LONG: [
        # too-long string property value in metadata
        {u"primary": valid_uuid, u"metadata": {u"foo": u"x" * 257}},
    ],
    INVALID_NUMERIC_TOO_LOW: [
        # too-small (but multiple of 1024) value for maximum size
        {u"primary": valid_uuid, u"maximum_size": 1024},
    ],
    INVALID_NUMERIC_NOT_MULTIPLE_OF: [
        # Value for maximum_size that is not a multiple of 1024 (but is larger
        # than the minimum allowed)
        {u"primary": valid_uuid, u"maximum_size": 1024 * 1024 * 64 + 1023},
    ],
    INVALID_STRING_PATTERN: [
        # too short string for dataset_id
        {u"primary": valid_uuid, u"dataset_id": valid_uuid[:35]},

        # too long string for dataset_id
        {u"primary": valid_uuid, u"dataset_id": valid_uuid + 'a'},

        # dataset_id not a valid UUID
        {u"primary": valid_uuid, u"dataset_id": bad_uuid_1},

        # non-IPv4-address for primary
        {u"primary": u"10.0.0.257",
         u"metadata": {},
         u"maximum_size": 1024 * 1024 * 1024,
         u"dataset_id": valid_uuid},

        {u"primary": u"example.com",
         u"metadata": {},
         u"maximum_size": 1024 * 1024 * 1024,
         u"dataset_id": valid_uuid},

    ],
    INVALID_WRONG_TYPE: [
        # wrong type for dataset_id
        {u"primary": valid_uuid, u"dataset_id": 10},

        # wrong type for metadata
        {u"primary": valid_uuid, u"metadata": 10},

        # wrong type for value in metadata
        {u"primary": valid_uuid, u"metadata": {u"foo": 10}},

        # wrong type for maximum size
        {u"primary": valid_uuid, u"maximum_size": u"123"},

        # wrong numeric type for maximum size
        {u"primary": valid_uuid, u"maximum_size": float(1024 * 1024 * 64)},

        # wrong type for primary
        {u"primary": 10,
         u"metadata": {},
         u"maximum_size": 1024 * 1024 * 1024,
         u"dataset_id": valid_uuid},

        # wrong type for deleted
        {u"primary": valid_uuid,
         u"deleted": u"hello"},
    ],
}

CONFIGURATION_DATASETS_UPDATE_PASSING_INSTANCES = [
    {},
    {u"primary": valid_uuid},
]

CONFIGURATION_DATASETS_UPDATE_FAILING_INSTANCES = {
    INVALID_OBJECT_PROPERTY_UNDEFINED: [
        {u"primary": valid_uuid, u'x': 1},
    ],
}

CONFIGURATION_DATASETS_PASSING_INSTANCES = [
    {u"primary": valid_uuid},

    # metadata is an object with a handful of short string key/values
    {u"primary": valid_uuid,
     u"metadata":
         dict.fromkeys((unicode(i) for i in range(16)), u"x" * 256)},

    # dataset_id is a string of 36 characters
    {u"primary": valid_uuid, u"dataset_id": valid_uuid},

    # deleted is a boolean
    {u"primary": valid_uuid, u"deleted": False},
    # maximum_size is an integer of at least 64MiB
    {u"primary": valid_uuid, u"maximum_size": 1024 * 1024 * 64},

    # maximum_size may be null, which means no size limit
    {u"primary": valid_uuid, u"maximum_size": None},

    # All of them can be combined.
    {u"primary": valid_uuid,
     u"metadata":
         dict.fromkeys((unicode(i) for i in range(16)), u"x" * 256),
     u"maximum_size": 1024 * 1024 * 64,
     u"dataset_id": valid_uuid,
     u"deleted": True},
]

ConfigurationDatasetsSchemaTests = build_schema_test(
    name="ConfigurationDatasetsSchemaTests",
    schema={'$ref':
            '/v1/endpoints.json#/definitions/configuration_datasets'},
    schema_store=SCHEMAS,
    failing_instances=CONFIGURATION_DATASETS_FAILING_INSTANCES,
    passing_instances=CONFIGURATION_DATASETS_PASSING_INSTANCES,
)


ConfigurationDatasetsUpdateSchemaTests = build_schema_test(
    name="ConfigurationDatasetsUpdateSchemaTests",
    schema={'$ref':
            '/v1/endpoints.json#/definitions/configuration_datasets_update'},
    schema_store=SCHEMAS,
    failing_instances=CONFIGURATION_DATASETS_UPDATE_FAILING_INSTANCES,
    passing_instances=CONFIGURATION_DATASETS_UPDATE_PASSING_INSTANCES,
)

CONFIGURATION_DATASETS_CREATE_FAILING_INSTANCES = (
    CONFIGURATION_DATASETS_FAILING_INSTANCES.copy()
)

CONFIGURATION_DATASETS_CREATE_FAILING_INSTANCES.setdefault(
    INVALID_OBJECT_PROPERTY_MISSING, []
).append(
    # primary is required for create
    {u"metadata": {},
     u"maximum_size": 1024 * 1024 * 1024,
     u"dataset_id": valid_uuid}
)

ConfigurationDatasetsCreateSchemaTests = build_schema_test(
    name="ConfigurationDatasetsCreateSchemaTests",
    schema={'$ref':
            '/v1/endpoints.json#/definitions/configuration_datasets_create'},
    schema_store=SCHEMAS,
    failing_instances=CONFIGURATION_DATASETS_CREATE_FAILING_INSTANCES,
    passing_instances=CONFIGURATION_DATASETS_PASSING_INSTANCES,
)

StateDatasetsArraySchemaTests = build_schema_test(
    name="StateDatasetsArraySchemaTests",
    schema={'$ref': '/v1/endpoints.json#/definitions/state_datasets_array'},
    schema_store=SCHEMAS,
    failing_instances={
        INVALID_OBJECT_PROPERTY_MISSING: [
            # missing dataset_id
            [{u"primary": valid_uuid,
              u"path": u"/123"}],
        ],
        INVALID_WRONG_TYPE: [
            # not an array
            {}, u"lalala", 123,

            # null primary
            [{u"primary": None,
              u"maximum_size": 1024 * 1024 * 1024,
              u"dataset_id": valid_uuid}],

            # null path
            [{u"path": None,
              u"maximum_size": 1024 * 1024 * 1024,
              u"dataset_id": valid_uuid}],

            # XXX Ideally there'd be a couple more tests here:
            # * primary without path
            # * path without primary
            # See FLOC-2170

            # wrong type for path
            [{u"primary": valid_uuid,
              u"dataset_id": valid_uuid,
              u"path": 123}],
        ],
    },
    passing_instances=[
        # missing primary and path
        [{u"maximum_size": 1024 * 1024 * 1024,
          u"dataset_id": valid_uuid}],

        # maximum_size is integer
        [{u"primary": valid_uuid,
          u"dataset_id": valid_uuid,
          u"path": u"/123",
          u"maximum_size": 1024 * 1024 * 64}],

        # multiple entries:
        [{u"primary": valid_uuid,
          u"dataset_id": valid_uuid,
          u"path": u"/123"},
         {u"primary": valid_uuid,
          u"dataset_id": valid_uuid,
          u"path": u"/123",
          u"maximum_size": 1024 * 1024 * 64}],
    ]
)

ConfigurationDatasetsListTests = build_schema_test(
    name="ConfigurationDatasetsListTests",
    schema={'$ref':
            '/v1/endpoints.json#/definitions/configuration_datasets_list'},
    schema_store=SCHEMAS,
    failing_instances={
        INVALID_NUMERIC_TOO_LOW: [
            # Failing dataset type (maximum_size less than minimum allowed)
            [{u"primary": valid_uuid, u"maximum_size": 123}],
        ],
        INVALID_WRONG_TYPE: [
            # Incorrect type
            {},
            # Wrong item type
            ["string"],
        ],
    },
    passing_instances=[
        [],
        [{u"primary": valid_uuid}],
        [{u"primary": valid_uuid}, {u"primary": valid_uuid}]
    ],
)

StateContainersArrayTests = build_schema_test(
    name="StateContainersArrayTests",
    schema={'$ref':
            '/v1/endpoints.json#/definitions/state_containers_array'},
    schema_store=SCHEMAS,
    failing_instances={
        INVALID_OBJECT_PROPERTY_MISSING: [
            # Failing dataset type (missing running)
            [{u"node_uuid": valid_uuid, u"name": u"lalala",
              u"image": u"busybox:latest"}]
        ],
        INVALID_WRONG_TYPE: [
            # Incorrect type
            {},
            # Wrong item type
            ["string"],
        ],
    },
    passing_instances=[
        [],
        [{u"name": u"lalala",
          u"node_uuid": valid_uuid,
          u"image": u"busybox:latest", u'running': True}],
        [{
            u"node_uuid": valid_uuid,
            u'image': u'nginx:latest',
            u'name': u'webserver2',
            u'running': True},
         {
             u"node_uuid": valid_uuid,
             u'image': u'nginx:latest',
             u'name': u'webserver',
             u'running': False}],
    ],
)


NodesTests = build_schema_test(
    name="NodesTests",
    schema={'$ref': '/v1/endpoints.json#/definitions/nodes_array'},
    schema_store=SCHEMAS,
    failing_instances={
        INVALID_OBJECT_PROPERTY_UNDEFINED: [
            # Extra key
            [{'host': '192.168.1.10', 'uuid': valid_uuid, 'x': 'y'}],
        ],
        INVALID_OBJECT_PROPERTY_MISSING: [
            # Missing host
            [{"uuid": valid_uuid}],
            # Missing uuid
            [{'host': '192.168.1.10'}],
        ],
        INVALID_WRONG_TYPE: [
            # Wrong type
            {'host': '192.168.1.10', 'uuid': valid_uuid},
            # Wrong uuid type
            [{'host': '192.168.1.10', 'uuid': 123}],
            # Wrong host type
            [{'host': 192, 'uuid': valid_uuid}],
        ],
    },
    passing_instances=[
        [],
        [{'host': '192.168.1.10', 'uuid': valid_uuid}],
        [{'host': '192.168.1.10', 'uuid': valid_uuid},
         {'host': '192.168.1.11', 'uuid': valid_uuid}],
    ],
)

NodeTests = build_schema_test(
    name="NodeTests",
    schema={'$ref': '/v1/endpoints.json#/definitions/node'},
    schema_store=SCHEMAS,
    failing_instances={
        INVALID_OBJECT_PROPERTY_UNDEFINED: [
            # Extra key
            {'uuid': valid_uuid, 'x': 'y'},
        ],
        INVALID_OBJECT_PROPERTY_MISSING: [
            # Missing uuid
            {},
        ],
        INVALID_WRONG_TYPE: [
            # Wrong type
            [], 1, None,
            # Wrong uuid type
            {'uuid': 123},
        ],
    },
    passing_instances=[
        {'uuid': valid_uuid},
    ],
)


LEASE_WITH_EXPIRATION = {'dataset_id': valid_uuid,
                         'node_uuid': valid_uuid,
                         'expires': 15}
# Can happen sometimes, means time went backwards or a bug but at least we
# should report things accurately.
LEASE_WITH_NEGATIVE_EXPIRATION = {'dataset_id': valid_uuid,
                                  'node_uuid': valid_uuid,
                                  'expires': -0.1}
LEASE_NO_EXPIRES = {'dataset_id': valid_uuid,
                    'node_uuid': valid_uuid,
                    'expires': None}
BAD_LEASES = {
    INVALID_OBJECT_PROPERTY_UNDEFINED: [
        # Extra key:
        {'dataset_id': valid_uuid, 'node_uuid': valid_uuid,
         'expires': None, 'extra': 'key'},
    ],
    INVALID_OBJECT_PROPERTY_MISSING: [
        # Missing dataset_id:
        {'node_uuid': valid_uuid, 'expires': None},
        # Missing node_uuid:
        {'dataset_id': valid_uuid, 'expires': None},
        # Missing expires:
        {'node_uuid': valid_uuid, 'dataset_id': valid_uuid},
    ],
    INVALID_WRONG_TYPE: [
        # Wrong types:
        None, [], 1,
        # Wrong type for dataset_id:
        {'node_uuid': valid_uuid, 'dataset_id': 123,
         'expires': None},
        # Wrong type for node_uuid:
        {'dataset_id': valid_uuid, 'node_uuid': 123,
         'expires': None},
        # Wrong type for expires:
        {'dataset_id': valid_uuid, 'node_uuid': valid_uuid,
         'expires': []},
    ],
}

BAD_LEASE_LISTS = {
    INVALID_WRONG_TYPE: [
        None, {}, 1
    ] + list([bad] for bad in BAD_LEASES)
}

ListLeasesTests = build_schema_test(
    name="ListLeasesTests",
    schema={'$ref': '/v1/endpoints.json#/definitions/list_leases'},
    schema_store=SCHEMAS,
    failing_instances=BAD_LEASE_LISTS,
    passing_instances=[
        [],
        [LEASE_NO_EXPIRES],
        [LEASE_WITH_EXPIRATION, LEASE_WITH_NEGATIVE_EXPIRATION],
    ],
)

# Endpoints that return a single lease: delete, create
LeaseResultTests = build_schema_test(
    name="LeaseResultTests",
    schema={'$ref': '/v1/endpoints.json#/definitions/lease'},
    schema_store=SCHEMAS,
    failing_instances=BAD_LEASES,
    passing_instances=[
        LEASE_NO_EXPIRES,
        LEASE_WITH_EXPIRATION,
        LEASE_WITH_NEGATIVE_EXPIRATION,
    ],
)
