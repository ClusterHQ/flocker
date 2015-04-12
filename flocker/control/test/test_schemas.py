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


ConfigurationContainersSchemaTests = build_schema_test(
    name="ConfigurationContainersUpdateSchemaTests",
    schema={
        '$ref':
            '/v1/endpoints.json#/definitions/configuration_container_update'
    },
    schema_store=SCHEMAS,
    failing_instances=[
        # Host missing
        {},
        # Host wrong type
        {u'host': 1},
        # Host not a host
        {u'host': u'idonotexist'},
        # Extra properties
        {u'host': u'192.168.0.3', u'image': u'nginx:latest'},
    ],
    passing_instances=[
        {u'host': u'192.168.0.3'},
    ],
)


ConfigurationContainersSchemaTests = build_schema_test(
    name="ConfigurationContainersSchemaTests",
    schema={'$ref': '/v1/endpoints.json#/definitions/configuration_container'},
    schema_store=SCHEMAS,
    failing_instances=[
        # Host wrong type
        {'host': 1, 'image': 'clusterhq/redis', 'name': 'my_container'},
        # Host not a host
        {
            'host': 'idonotexist',
            'image': 'clusterhq/redis',
            'name': 'my_container'
        },
        # Name wrong type
        {'host': '192.168.0.3', 'image': 'clusterhq/redis', 'name': 1},
        # Image wrong type
        {'host': '192.168.0.3', 'image': 1, 'name': 'my_container'},
        # Name missing
        {'host': '192.168.0.3', 'image': 'clusterhq/redis'},
        # Host missing
        {'image': 'clusterhq/redis', 'name': 'my_container'},
        # Image missing
        {'host': '192.168.0.3', 'name': 'my_container'},
        # Name not valid
        {'host': '192.168.0.3', 'image': 'clusterhq/redis', 'name': '@*!'},
        # Ports given but not a list of mappings
        {
            'host': '192.168.0.3',
            'image': 'postgres',
            'name': 'postgres',
            'ports': 'I am not a list of port maps'
        },
        # Ports given but internal is not valid
        {
            'host': '192.168.0.3',
            'image': 'postgres',
            'name': 'postgres',
            'ports': [{'internal': 'xxx', 'external': 8080}]
        },
        # Ports given but external is not valid
        {
            'host': '192.168.0.3',
            'image': 'postgres',
            'name': 'postgres',
            'ports': [{'internal': 80, 'external': '1'}]
        },
        # Ports given but invalid key present
        {
            'host': '192.168.0.3',
            'image': 'postgres',
            'name': 'postgres',
            'ports': [{'container': 80, 'external': '1'}]
        },
        # Ports given but external is not valid integer
        {
            'host': '192.168.0.3',
            'image': 'postgres',
            'name': 'postgres',
            'ports': [{'internal': 80, 'external': 22.5}]
        },
        # Ports given but not unique
        {
            'host': '192.168.0.3',
            'image': 'postgres',
            'name': 'postgres',
            'ports': [
                {'internal': 80, 'external': 8080},
                {'internal': 80, 'external': 8080},
            ]
        },
        # Environment given but not a dict
        {
            'host': '192.168.0.3',
            'image': 'postgres',
            'name': 'postgres',
            'environment': 'x=y'
        },
        # Environment given but at least one entry is not a string
        {
            'host': '192.168.0.3',
            'image': 'postgres',
            'name': 'postgres',
            'environment': {
                'POSTGRES_USER': 'admin',
                'POSTGRES_VERSION': 9.4
            }
        },
        # Restart policy given but not a string
        {
            'host': '192.168.0.3',
            'image': 'postgres',
            'name': 'postgres',
            'restart_policy': 1
        },
        # Restart policy string given but not an allowed value
        {
            'host': '192.168.0.3',
            'image': 'postgres',
            'name': 'postgres',
            'restart_policy': {"name": "no restart"}
        },
        # Restart policy is on-failure but max retry count is negative
        {
            'host': '192.168.0.3',
            'image': 'postgres',
            'name': 'postgres',
            'restart_policy': {
                "name": "on-failure", "maximum_retry_count": -1
            }
        },
        # Restart policy is on-failure but max retry count is NaN
        {
            'host': '192.168.0.3',
            'image': 'postgres',
            'name': 'postgres',
            'restart_policy': 'on-failure',
            'restart_policy': {
                "name": "on-failure", "maximum_retry_count": "15"
            }
        },
        # Restart policy has max retry count but no name
        {
            'host': '192.168.0.3',
            'image': 'postgres',
            'name': 'postgres',
            'restart_policy': 'on-failure',
            'restart_policy': {
                "maximum_retry_count": 15
            }
        },
        # CPU shares given but not an integer
        {
            'host': '192.168.0.3',
            'image': 'postgres',
            'name': 'postgres',
            'cpu_shares': '512'
        },
        # CPU shares given but negative
        {
            'host': '192.168.0.3',
            'image': 'postgres',
            'name': 'postgres',
            'cpu_shares': -512
        },
        # CPU shares given but greater than max
        {
            'host': '192.168.0.3',
            'image': 'postgres',
            'name': 'postgres',
            'cpu_shares': 1025
        },
        # Memory limit given but not an integer
        {
            'host': '192.168.0.3',
            'image': 'postgres',
            'name': 'postgres',
            'memory_limit': '250MB'
        },
        # Memory limit given but negative
        {
            'host': '192.168.0.3',
            'image': 'postgres',
            'name': 'postgres',
            'memory_limit': -1024
        },
        # Links given but not a list
        {
            'host': '192.168.0.3',
            'image': 'nginx:latest',
            'name': 'webserver',
            'links': {
                'alias': 'postgres',
                'local_port': 5432,
                'remote_port': 54320
            }
        },
        # Links given but alias missing
        {
            'host': '192.168.0.3',
            'image': 'nginx:latest',
            'name': 'webserver',
            'links': [{
                'local_port': 5432,
                'remote_port': 54320
            }]
        },
        # Links given but local port missing
        {
            'host': '192.168.0.3',
            'image': 'nginx:latest',
            'name': 'webserver',
            'links': [{
                'alias': 'postgres',
                'remote_port': 54320
            }]
        },
        # Links given but remote port missing
        {
            'host': '192.168.0.3',
            'image': 'nginx:latest',
            'name': 'webserver',
            'links': [{
                'alias': 'postgres',
                'local_port': 5432,
            }]
        },
        # Links given but alias is not a string
        {
            'host': '192.168.0.3',
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
            'host': '192.168.0.3',
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
            'host': '192.168.0.3',
            'image': 'nginx:latest',
            'name': 'webserver',
            'links': [{
                'alias': 'postgres',
                'local_port': 5432,
                'remote_port': '54320'
            }]
        },
        # Links given but local port is greater than max (65535)
        {
            'host': '192.168.0.3',
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
            'host': '192.168.0.3',
            'image': 'nginx:latest',
            'name': 'webserver',
            'links': [{
                'alias': 'postgres',
                'local_port': 5432,
                'remote_port': 65536
            }]
        },
        # Volume with dataset_id of wrong type
        {
            'host': '192.168.0.3',
            'image': 'postgres',
            'name': 'postgres',
            'volumes': [{'dataset_id': 123,
                         'mountpoint': '/var/db'}],
        },
        # Volume with mountpoint of wrong type
        {
            'host': '192.168.0.3',
            'image': 'postgres',
            'name': 'postgres',
            'volumes': [{'dataset_id': "x" * 36,
                         'mountpoint': 123}],
        },
        # Volume missing dataset_id
        {
            'host': '192.168.0.3',
            'image': 'postgres',
            'name': 'postgres',
            'volumes': [{'mountpoint': '/var/db'}],
        },
        # Volume missing mountpoint
        {
            'host': '192.168.0.3',
            'image': 'postgres',
            'name': 'postgres',
            'volumes': [{'dataset_id': "x" * 36}],
        },
        # Volume with extra field
        {
            'host': '192.168.0.3',
            'image': 'postgres',
            'name': 'postgres',
            'volumes': [{'dataset_id': "x" * 36,
                         'mountpoint': '/var/db',
                         'extra': 'value'}],
        },
        # More than one volume (this will eventually work - see FLOC-49)
        {
            'host': '192.168.0.3',
            'image': 'postgres',
            'name': 'postgres',
            'volumes': [{'dataset_id': "x" * 36,
                         'mountpoint': '/var/db'},
                        {'dataset_id': "y" * 36,
                         'mountpoint': '/var/db2'}],
        },
        # Path doesn't start with /
        {
            'host': '192.168.0.3',
            'image': 'postgres',
            'name': 'postgres',
            'volumes': [{'dataset_id': "y" * 36,
                         'mountpoint': 'var/db2'}],
        },
    ],
    passing_instances=[
        {
            'host': '192.168.0.3',
            'image': 'postgres',
            'name': 'postgres'
        },
        {
            'host': '192.168.0.3',
            'image': 'docker/postgres',
            'name': 'postgres'
        },
        {
            'host': '192.168.0.3',
            'image': 'docker/postgres:latest',
            'name': 'postgres'
        },
        {
            'host': '192.168.0.3',
            'image': 'postgres',
            'name': 'postgres',
            'ports': [{'internal': 80, 'external': 8080}]
        },
        {
            'host': '192.168.0.3',
            'image': 'postgres',
            'name': 'postgres',
            'ports': [
                {'internal': 80, 'external': 8080},
                {'internal': 3306, 'external': 42000}
            ]
        },
        {
            'host': '192.168.0.3',
            'image': 'postgres',
            'name': 'postgres',
            'environment': {
                'POSTGRES_USER': 'admin',
                'POSTGRES_VERSION': '9.4'
            }
        },
        {
            'host': '192.168.0.3',
            'image': 'docker/postgres:latest',
            'name': 'postgres',
            'restart_policy': {'name': 'never'}
        },
        {
            'host': '192.168.0.3',
            'image': 'docker/postgres:latest',
            'name': 'postgres',
            'restart_policy': {'name': 'always'}
        },
        {
            'host': '192.168.0.3',
            'image': 'docker/postgres:latest',
            'name': 'postgres',
            'restart_policy': {'name': 'on-failure'}
        },
        {
            'host': '192.168.0.3',
            'image': 'docker/postgres:latest',
            'name': 'postgres',
            'restart_policy': {
                'name': 'on-failure', 'maximum_retry_count': 5
            }
        },
        {
            'host': '192.168.0.3',
            'image': 'docker/postgres:latest',
            'name': 'postgres',
            'cpu_shares': 512
        },
        {
            'host': '192.168.0.3',
            'image': 'docker/postgres:latest',
            'name': 'postgres',
            'memory_limit': 262144000
        },
        {
            'host': '192.168.0.3',
            'image': 'nginx:latest',
            'name': 'webserver',
            'links': [{
                'alias': 'postgres',
                'local_port': 5432,
                'remote_port': 54320
            }]
        },
        {
            'host': '192.168.0.3',
            'image': 'postgres',
            'name': 'postgres',
            'volumes': [{'dataset_id': "x" * 36,
                         'mountpoint': '/var/db'}],
        },
        {
            'host': '192.168.0.3',
            'image': 'postgres',
            'name': 'postgres',
            'volumes': [],
        },
    ],
)

CONFIGURATION_DATASETS_FAILING_INSTANCES = [
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

    # wrong type for deleted
    {u"primary": u"10.0.0.1",
     u"deleted": u"hello"},
]

CONFIGURATION_DATASETS_PASSING_INSTANCES = [
    # everything optional except primary
    {u"primary": u"10.0.0.1"},

    # metadata is an object with a handful of short string key/values
    {u"primary": u"10.0.0.1",
     u"metadata":
         dict.fromkeys((unicode(i) for i in range(16)), u"x" * 256)},

    # maximum_size is an integer of at least 64MiB
    {u"primary": u"10.0.0.1", u"maximum_size": 1024 * 1024 * 64},

    # maximum_size may be null, which means no size limit
    {u"primary": u"10.0.0.1", u"maximum_size": None},

    # dataset_id is a string of 36 characters
    {u"primary": u"10.0.0.1", u"dataset_id": u"x" * 36},

    # deleted is a boolean
    {u"primary": u"10.0.0.1", u"deleted": False},

    # All of them can be combined.
    {u"primary": u"10.0.0.1",
     u"metadata":
         dict.fromkeys((unicode(i) for i in range(16)), u"x" * 256),
     u"maximum_size": 1024 * 1024 * 64,
     u"dataset_id": u"x" * 36,
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
    failing_instances=CONFIGURATION_DATASETS_FAILING_INSTANCES,
    passing_instances=CONFIGURATION_DATASETS_PASSING_INSTANCES,
)


ConfigurationDatasetsCreateSchemaTests = build_schema_test(
    name="ConfigurationDatasetsCreateSchemaTests",
    schema={'$ref':
            '/v1/endpoints.json#/definitions/configuration_datasets_create'},
    schema_store=SCHEMAS,
    failing_instances=(
        CONFIGURATION_DATASETS_FAILING_INSTANCES + [
            # missing primary
            {u"metadata": {},
             u"maximum_size": 1024 * 1024 * 1024,
             u"dataset_id": u"x" * 36},
        ]
    ),
    passing_instances=CONFIGURATION_DATASETS_PASSING_INSTANCES,
)

StateDatasetsArraySchemaTests = build_schema_test(
    name="StateDatasetsArraySchemaTests",
    schema={'$ref': '/v1/endpoints.json#/definitions/state_datasets_array'},
    schema_store=SCHEMAS,
    failing_instances=[
        # not an array
        {}, u"lalala", 123,

        # missing primary
        [{u"path": u"/123",
          u"maximum_size": 1024 * 1024 * 1024,
          u"dataset_id": u"x" * 36}],

        # missing dataset_id
        [{u"primary": u"10.0.0.1",
          u"path": u"/123"}],

        # wrong type for path
        [{u"primary": u"10.0.0.1",
          u"dataset_id": u"x" * 36,
          u"path": 123}],

        # missing path
        [{u"primary": u"10.0.0.1",
          u"dataset_id": u"x" * 36}],
    ],

    passing_instances=[
        # only maximum_size is optional
        [{u"primary": u"10.0.0.1",
          u"dataset_id": u"x" * 36,
          u"path": u"/123"}],

        # maximum_size is integer
        [{u"primary": u"10.0.0.1",
          u"dataset_id": u"x" * 36,
          u"path": u"/123",
          u"maximum_size": 1024 * 1024 * 64}],

        # multiple entries:
        [{u"primary": u"10.0.0.1",
          u"dataset_id": u"x" * 36,
          u"path": u"/123"},
         {u"primary": u"10.0.0.1",
          u"dataset_id": u"y" * 36,
          u"path": u"/123",
          u"maximum_size": 1024 * 1024 * 64}],
    ]
)

ConfigurationDatasetsListTests = build_schema_test(
    name="ConfigurationDatasetsListTests",
    schema={'$ref':
            '/v1/endpoints.json#/definitions/configuration_datasets_list'},
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

StateContainersArrayTests = build_schema_test(
    name="StateContainersArrayTests",
    schema={'$ref':
            '/v1/endpoints.json#/definitions/state_containers_array'},
    schema_store=SCHEMAS,
    failing_instances=[
        # Incorrect type
        {},
        # Wrong item type
        ["string"],
        # Failing dataset type (missing running)
        [{u"host": u"10.0.0.1", u"name": u"lalala",
          u"image": u"busybox:latest"}]
    ],
    passing_instances=[
        [],
        [{u"host": u"10.0.0.1", u"name": u"lalala",
          u"image": u"busybox:latest", u'running': True}],
        [{
            u'host': u'192.168.0.3',
            u'image': u'nginx:latest',
            u'name': u'webserver2',
            u'running': True},
         {
             u'host': u'192.168.0.3',
             u'image': u'nginx:latest',
             u'name': u'webserver',
             u'running': False}],
    ],
)
