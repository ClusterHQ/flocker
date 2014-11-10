# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.node._config``.
"""

from __future__ import unicode_literals, absolute_import

import copy

from twisted.python.filepath import FilePath
from twisted.trial.unittest import SynchronousTestCase
from yaml import safe_load
from .._config import (
    ConfigurationError, FlockerConfiguration, marshal_configuration,
    current_from_configuration, deployment_from_configuration,
    model_from_configuration, FigConfiguration,
    applications_to_flocker_yaml
)
from .._model import (
    Application, AttachedVolume, DockerImage, Deployment, Node, Port, Link,
    NodeState,
)


class ApplicationsToFlockerYAMLTests(SynchronousTestCase):
    """
    Tests for ``applications_to_flocker_yaml``.
    """
    def test_returns_valid_yaml(self):
        """
        The YAML returned by ``applications_to_flocker_yaml" can be
        successfully parsed as YAML.
        """
        expected = {
            'version': 1,
            'applications': {
                'wordpress': {
                    'image': 'sample/wordpress:latest',
                    'volume': {'mountpoint': b'/var/www/wordpress'},
                    'environment': {'WORDPRESS_ADMIN_PASSWORD': 'admin'},
                    'ports': [{'internal': 80, 'external': 8080}],
                    'links': [
                        {'local_port': 3306,
                         'remote_port': 3306,
                         'alias': 'db'},
                        {'local_port': 3307,
                         'remote_port': 3307,
                         'alias': 'db'}
                    ]
                },
                'mysql': {
                    'image': 'sample/mysql:latest',
                    'ports': [
                        {'internal': 3306, 'external': 3306},
                        {'internal': 3307, 'external': 3307}
                    ],
                }
            }
        }
        config = copy.deepcopy(expected)
        applications = FlockerConfiguration(config).applications()
        yaml = safe_load(applications_to_flocker_yaml(applications))
        self.assertEqual(yaml, expected)

    def test_not_fig_yaml(self):
        """
        Parsed YAML returned by ``applications_to_flocker_yaml`` is
        identified as non-fig by ``FigConfiguration.is_valid_format``.
        """
        config = {
            'version': 1,
            'applications': {
                'postgres':
                    {'image': 'sample/postgres'}
            }
        }
        applications = FlockerConfiguration(config).applications()
        yaml = applications_to_flocker_yaml(applications)
        parsed = safe_load(yaml)
        parser = FigConfiguration(parsed)
        self.assertFalse(parser.is_valid_format())

    def test_valid_flocker_yaml(self):
        """
        Parsed YAML returned by `applications_to_flocker_yaml`` is
        validated by ``Configuration.is_valid_format``.
        """
        config = {
            'version': 1,
            'applications': {
                'postgres':
                    {'image': 'sample/postgres'}
            }
        }
        applications = FlockerConfiguration(config).applications()
        yaml = applications_to_flocker_yaml(applications)
        parsed = safe_load(yaml)
        parser = FlockerConfiguration(parsed)
        self.assertTrue(parser.is_valid_format())

    def test_applications_from_converted_flocker(self):
        """
        Parsed YAML returned by ``applications_to_flocker_yaml`` is
        translated to a ``dict`` of ``Application`` instances by
        ``FlockerConfiguration.applications``.
        """
        config = {
            'version': 1,
            'applications': {
                'postgres':
                    {'image': 'sample/postgres'}
            }
        }
        applications = FlockerConfiguration(config).applications()
        yaml = applications_to_flocker_yaml(applications)
        parsed = safe_load(yaml)
        parser = FlockerConfiguration(parsed)
        expected = {
            'postgres': Application(
                name='postgres',
                image=DockerImage(repository='sample/postgres', tag='latest'),
                ports=frozenset(),
                links=frozenset(),
                environment=None,
                volume=None
            )
        }
        applications = parser.applications()
        self.assertEqual(applications, expected)

    def test_has_version(self):
        """
        The YAML returned by ``applications_to_flocker_yaml`` contains
        a version entry.
        """
        config = {
            'version': 1,
            'applications': {
                'postgres':
                    {'image': 'sample/postgres'}
            }
        }
        applications = FlockerConfiguration(config).applications()
        yaml = applications_to_flocker_yaml(applications)
        parsed = safe_load(yaml)
        self.assertTrue('version' in parsed)

    def test_has_applications(self):
        """
        The YAML returned by ``applications_to_flocker_yaml`` contains
        an applications entry.
        """
        config = {
            'version': 1,
            'applications': {
                'postgres':
                    {'image': 'sample/postgres'}
            }
        }
        applications = FlockerConfiguration(config).applications()
        yaml = applications_to_flocker_yaml(applications)
        parsed = safe_load(yaml)
        self.assertTrue('applications' in parsed)

    def test_has_image(self):
        """
        The YAML for a single application entry returned by
        ``applications_to_flocker_yaml`` contains an image entry
        that holds the image name in image:tag format.
        """
        config = {
            'version': 1,
            'applications': {
                'postgres':
                    {'image': 'sample/postgres'}
            }
        }
        applications = FlockerConfiguration(config).applications()
        yaml = applications_to_flocker_yaml(applications)
        parsed = safe_load(yaml)
        self.assertEqual(
            parsed['applications']['postgres']['image'],
            'sample/postgres:latest'
        )

    def test_has_links(self):
        """
        The YAML for a single application entry returned by
        ``applications_to_flocker_yaml`` contains a links entry.
        """
        config = {
            'version': 1,
            'applications': {
                'wordpress': {
                    'environment': {'WORDPRESS_ADMIN_PASSWORD': 'admin'},
                    'volume': {'mountpoint': b'/var/www/wordpress'},
                    'image': 'sample/wordpress',
                    'ports': [{'internal': 80, 'external': 8080}],
                    'links': [
                        {'alias': 'db', 'local_port': 3306,
                         'remote_port': 3306},
                        {'alias': 'db', 'local_port': 3307,
                         'remote_port': 3307}
                    ],
                },
                'mysql': {
                    'image': 'sample/mysql',
                    'ports': [
                        {'internal': 3306, 'external': 3306},
                        {'internal': 3307, 'external': 3307}
                    ],
                }
            }
        }
        expected_links = [
            {'alias': 'db', 'local_port': 3306, 'remote_port': 3306},
            {'alias': 'db', 'local_port': 3307, 'remote_port': 3307}
        ]
        applications = FlockerConfiguration(config).applications()
        yaml = applications_to_flocker_yaml(applications)
        parsed = safe_load(yaml)
        self.assertEqual(
            parsed['applications']['wordpress']['links'],
            expected_links
        )

    def test_has_ports(self):
        """
        The YAML for a single application entry returned by
        ``applications_to_flocker_yaml`` contains a ports entry,
        mapping ports to the format used by Flocker.
        """
        config = {
            'version': 1,
            'applications': {
                'postgres':
                    {'image': 'sample/postgres',
                     'ports': [{'internal': 5432, 'external': 5433}]}
            }
        }
        applications = FlockerConfiguration(config).applications()
        yaml = applications_to_flocker_yaml(applications)
        parsed = safe_load(yaml)
        self.assertEqual(
            parsed['applications']['postgres']['ports'],
            [{'external': 5433, 'internal': 5432}]
        )

    def test_has_environment(self):
        """
        The YAML for a single application entry returned by
        ``applications_to_flocker_yaml`` contains an environment entry.
        """
        config = {
            'version': 1,
            'applications': {
                'postgres': {
                    'image': 'sample/postgres',
                    'ports': [{'internal': 5432, 'external': 5432}],
                    'environment': {'PGSQL_USER_PASSWORD': 'clusterhq'},
                }
            }
        }
        applications = FlockerConfiguration(config).applications()
        yaml = applications_to_flocker_yaml(applications)
        parsed = safe_load(yaml)
        self.assertEqual(
            parsed['applications']['postgres']['environment'],
            {'PGSQL_USER_PASSWORD': 'clusterhq'}
        )

    def test_has_volume(self):
        """
        The YAML for a single application entry returned by
        ``applications_to_flocker_yaml`` contains a volume entry
        that matches the Flocker-format.
        """
        config = {
            'version': 1,
            'applications': {
                'postgres': {
                    'image': 'sample/postgres',
                    'ports': [{'internal': 5432, 'external': 5432}],
                    'volume': {'mountpoint': b'/var/lib/data'},
                }
            }
        }
        applications = FlockerConfiguration(config).applications()
        yaml = applications_to_flocker_yaml(applications)
        parsed = safe_load(yaml)
        self.assertEqual(
            parsed['applications']['postgres']['volume'],
            {'mountpoint': '/var/lib/data'}
        )


class ApplicationsFromFigConfigurationTests(SynchronousTestCase):
    """
    Tests for ``Configuration._applications_from_configuration``.
    """
    def test_valid_fig_config_detected_on_image(self):
        """
        A top-level dictionary with any arbitrary key containing another
        dictionary with an "image" key is detected as a valid fig format.

        Note that "valid fig-format" does not necessarily translate to
        "valid configuration", it just means that the suppled configuration
        will be treated and parsed as fig-format rather than flocker-format.

        A valid fig-style configuration is defined as:
        Overall application configuration is of type dictionary, containing
        one or more keys which each contain a further dictionary, which
        contain exactly one "image" key or "build" key and does not contain
        any invalid keys.
        """
        config = {
            'postgres':
                {'image': 'sample/postgres'}
        }
        parser = FigConfiguration(config)
        self.assertTrue(parser.is_valid_format())

    def test_valid_fig_config_detected_on_build(self):
        """
        A top-level dictionary with any arbitrary key containing another
        dictionary with a "build" key is detected as a valid fig format.
        """
        config = {
            'postgres':
                {'build': '.'}
        }
        parser = FigConfiguration(config)
        self.assertTrue(parser.is_valid_format())

    def test_dict_of_applications_from_fig(self):
        """
        ``Configuration.applications_from_configuration`` returns a
        ``dict`` of ``Application`` instances, one for each application key
        in the supplied configuration.
        """
        config = {
            'wordpress': {
                'environment': {'WORDPRESS_ADMIN_PASSWORD': 'admin'},
                'volumes': ['/var/www/wordpress'],
                'image': 'sample/wordpress',
                'ports': ['8080:80'],
                'links': ['mysql:db'],
            },
            'mysql': {
                'image': 'sample/mysql',
                'ports': ['3306:3306', '3307:3307'],
            }
        }
        expected_applications = {
            'wordpress': Application(
                name='wordpress',
                image=DockerImage(repository='sample/wordpress', tag='latest'),
                ports=frozenset([Port(internal_port=80,
                                      external_port=8080)]),
                links=frozenset([Link(local_port=3306, remote_port=3306,
                                      alias=u'db'),
                                 Link(local_port=3307, remote_port=3307,
                                      alias=u'db')]),
                environment=frozenset(
                    config['wordpress']['environment'].items()
                ),
                volume=AttachedVolume(
                    name='wordpress',
                    mountpoint=FilePath(b'/var/www/wordpress'))),
            'mysql': Application(
                name='mysql',
                image=DockerImage(repository='sample/mysql', tag='latest'),
                ports=frozenset([Port(internal_port=3306,
                                      external_port=3306),
                                 Port(internal_port=3307,
                                      external_port=3307)]),
                environment=None,
                links=frozenset(),
                volume=None),
        }
        parser = FigConfiguration(config)
        applications = parser.applications()
        self.assertEqual(expected_applications, applications)

    def test_valid_fig_config_environment(self):
        """
        ``FigConfiguration._parse_app_environment`` returns a ``frozenset``
        of environment variable name/value pairs given a valid configuration.
        """
        config = {
            'postgres': {
                'image': 'sample/postgres',
                'environment': {
                    'PG_SCHEMA_NAME': 'example_database',
                    'PG_PGUSER_PASSWORD': 'clusterhq'
                }
            }
        }
        parser = FigConfiguration(config)
        expected_result = frozenset(
            config['postgres']['environment'].items()
        )
        environment = parser._parse_app_environment(
            'postgres',
            config['postgres']['environment']
        )
        self.assertEqual(expected_result, environment)

    def test_valid_fig_config_volumes(self):
        """
        ``FigConfiguration._parse_app_volumes`` returns a ``AttachedVolume``
        instance containing the volume mountpoint given a valid configuration.
        """
        config = {
            'postgres': {
                'image': 'sample/postgres',
                'volumes': [b'/var/db/data']
            }
        }
        parser = FigConfiguration(config)
        expected_result = AttachedVolume(
            name='postgres',
            mountpoint=FilePath(b'/var/db/data')
        )
        volume = parser._parse_app_volumes(
            'postgres',
            config['postgres']['volumes']
        )
        self.assertEqual(expected_result, volume)

    def test_valid_fig_config_ports(self):
        """
        ``FigConfiguration._parse_app_ports`` returns a ``list``
        of ``Port`` objects mapping internal and external ports, given a
        valid configuration.
        """
        config = {
            'postgres': {
                'image': 'sample/postgres',
                'ports': [b'8080:80']
            }
        }
        parser = FigConfiguration(config)
        expected_result = [
            Port(internal_port=80, external_port=8080)
        ]
        ports = parser._parse_app_ports(
            'postgres',
            config['postgres']['ports']
        )
        self.assertEqual(expected_result, ports)

    def test_valid_fig_config_links(self):
        """
        ``FigConfiguration._parse_app_links`` creates a ``dict`` mapping
        linked application names and aliases to each application, given a
        valid configuration.
        """
        config = {
            'postgres': {
                'image': 'sample/postgres',
                'volumes': [b'/var/db/data']
            },
            'wordpress': {
                'image': 'sample/wordpress',
                'links': [b'postgres:db']
            }
        }
        parser = FigConfiguration(config)
        parser._application_links['wordpress'] = []
        parser._parse_app_links(
            'wordpress',
            config['wordpress']['links']
        )
        expected_result = {
            u'wordpress': [
                {u'alias': u'db', u'target_application': u'postgres'},
            ]
        }
        self.assertEqual(expected_result, parser._application_links)

    def test_invalid_fig_config_image_and_build(self):
        """
        A fig-compatible application definition may not have both "image" and
        "build" keys.
        """
        config = {
            'postgres':
                {'build': '.', 'image': 'sample/postgres'}
        }
        parser = FigConfiguration(config)
        exception = self.assertRaises(
            ConfigurationError,
            parser.is_valid_format
        )
        error_message = (
            "Application 'postgres' has a config error. "
            "Must specify either 'build' or 'image'; found both."
        )
        self.assertEqual(exception.message, error_message)

    def test_invalid_fig_config_uses_build(self):
        """
        An ``ConfigurationError`` exception is raised if a fig-compatible
        application configuration uses the 'build' directive, which is not
        yet supported by Flocker.
        """
        config = {
            'postgres':
                {
                    'build': '.',
                    'dns': '8.8.8.8',
                    'expose': ['5432'],
                    'entrypoint': '/entry.sh',
                }
        }
        parser = FigConfiguration(config)
        exception = self.assertRaises(
            ConfigurationError,
            parser.applications
        )
        error_message = (
            "Application 'postgres' has a config error. "
            "'build' is not supported yet; please specify 'image'."
        )
        self.assertEqual(exception.message, error_message)

    def test_invalid_fig_config_unsupported_keys(self):
        """
        An ``ConfigurationError`` exception is raised if a fig-compatible
        application configuration contains keys for fig features that are
        not yet supported by Flocker.
        """
        config = {
            'postgres':
                {
                    'image': 'sample/postgres',
                    'dns': '8.8.8.8',
                    'expose': ['5432'],
                    'entrypoint': '/entry.sh',
                }
        }
        parser = FigConfiguration(config)
        exception = self.assertRaises(
            ConfigurationError,
            parser.applications
        )
        error_message = (
            "Application 'postgres' has a config error. "
            "Unsupported fig keys found: dns, entrypoint, expose"
        )
        self.assertEqual(exception.message, error_message)

    def test_invalid_fig_config_app_not_dict(self):
        """
        If the application config is not a dictionary, a
        ``ConfigurationError`` is raised.
        """
        config = ['wordpress', {"image": "sample/wordpress"}]
        exception = self.assertRaises(
            ConfigurationError,
            FigConfiguration,
            config
        )
        error_message = ("Application configuration must be "
                         "a dictionary, got list.")
        self.assertEqual(exception.message, error_message)

    def test_invalid_fig_config_value_not_dict(self):
        """
        If the application config is a fig-compatible dictionary with one or
        more arbitrary keys (representing app labels) but the value of any key
        is not itself a dictionary, a ``ConfigurationError`` is raised.
        """
        config = {
            'postgres': {
                'image': 'sample/postgres',
            },
            'wordpress': str("a string")
        }
        parser = FigConfiguration(config)
        exception = self.assertRaises(
            ConfigurationError,
            parser.applications,
        )
        error_message = (
            "Application 'wordpress' has a config error. "
            "Application configuration must be dictionary; got type 'str'."
        )
        self.assertEqual(exception.message, error_message)

    def test_invalid_fig_config_missing_image_or_build(self):
        """
        A single fig application configuration is not valid if it does not
        contain exactly one of an "image" key.
        If this is detected, ``ConfigurationError``        is raised.

        This condition can occur if ``_is_fig_configuration`` has
        detected a potentially valid fig-style configuration in that there
        is at least one application that meets the requirement of having an
        image or build key, but the overall configuration also contains
        another application that does not have a required key.
        """
        config = {
            'postgres': {
                'image': 'sample/postgres',
            },
            'wordpress': {
                'ports': ['8080:80'],
                'volumes': ['/var/www/wordpress']
            }
        }
        parser = FigConfiguration(config)
        exception = self.assertRaises(
            ConfigurationError,
            parser.applications,
        )
        error_message = (
            "Application 'wordpress' has a config error. "
            "Application configuration must contain either an "
            "'image' or 'build' key."
        )
        self.assertEqual(exception.message, error_message)

    def test_invalid_fig_config_unrecognised_key(self):
        """
        A single fig application configuration is not valid if it contains
        any keys besides "image", "environment", "ports", "volumes" or
        "links". If an invalid key is detected, ``ConfigurationError``
        is raised.
        """
        config = {
            'wordpress': {
                'environment': {'WORDPRESS_ADMIN_PASSWORD': 'admin'},
                'volumes': ['/var/www/wordpress'],
                'image': 'sample/wordpress',
                'ports': ['8080:80'],
                'foo': 'bar',
                'spam': 'eggs',
            }
        }
        parser = FigConfiguration(config)
        exception = self.assertRaises(
            ConfigurationError,
            parser.applications,
        )
        error_message = (
            "Application 'wordpress' has a config error. "
            "Unrecognised keys: foo, spam"
        )
        self.assertEqual(exception.message, error_message)

    def test_invalid_fig_config_ports_not_list(self):
        """
        A ``ConfigurationError`` is raised if the "ports" key of a fig
        compatible application config is not a list.
        """
        config = {
            'wordpress': {
                'environment': {'WORDPRESS_ADMIN_PASSWORD': 'admin'},
                'volumes': ['/var/www/wordpress'],
                'image': 'sample/wordpress',
                'ports': str('8080:80'),
            }
        }
        parser = FigConfiguration(config)
        exception = self.assertRaises(
            ConfigurationError,
            parser.applications,
        )
        error_message = (
            "Application 'wordpress' has a config error. "
            "'ports' must be a list; got type 'str'."
        )
        self.assertEqual(exception.message, error_message)

    def test_invalid_fig_config_malformed_ports(self):
        """
        A single fig application config is not valid if the "ports" key
        is present and the value is not a string in "host:container" format.
        If an invalid ports config is detected, ``ConfigurationError``
        is raised.
        """
        config = {
            'wordpress': {
                'environment': {'WORDPRESS_ADMIN_PASSWORD': 'admin'},
                'volumes': ['/var/www/wordpress'],
                'image': 'sample/wordpress',
                'ports': ['8080,80'],
            }
        }
        parser = FigConfiguration(config)
        exception = self.assertRaises(
            ConfigurationError,
            parser.applications,
        )
        error_message = (
            "Application 'wordpress' has a config error. "
            "'ports' must be list of string values in the form of "
            "'host_port:container_port'."
        )
        self.assertEqual(exception.message, error_message)

    def test_invalid_fig_config_ports_not_integers(self):
        """
        A ``ConfigurationError`` is raised if the parsed "ports" string
        in a fig application config is not a pair of integer values.
        """
        config = {
            'wordpress': {
                'environment': {'WORDPRESS_ADMIN_PASSWORD': 'admin'},
                'volumes': ['/var/www/wordpress'],
                'image': 'sample/wordpress',
                'ports': ['foo:bar'],
            }
        }
        parser = FigConfiguration(config)
        exception = self.assertRaises(
            ConfigurationError,
            parser.applications,
        )
        error_message = (
            "Application 'wordpress' has a config error. "
            "'ports' value 'foo:bar' could not be parsed "
            "in to integer values."
        )
        self.assertEqual(exception.message, error_message)

    def test_invalid_fig_config_links_not_list(self):
        """
        A ``ConfigurationError`` is raised if the "links" key of a fig
        compatible application config is not a list.
        """
        config = {
            'postgres': {
                'environment': {'PG_ROOT_PASSWORD': 'clusterhq'},
                'image': 'sample/postgres',
                'ports': ['54320:5432'],
                'volumes': ['/var/lib/pgsql'],
                'links': str('wordpress'),
            }
        }
        parser = FigConfiguration(config)
        exception = self.assertRaises(
            ConfigurationError,
            parser.applications,
        )
        error_message = (
            "Application 'postgres' has a config error. "
            "'links' must be a list; got type 'str'."
        )
        self.assertEqual(exception.message, error_message)

    def test_invalid_fig_config_links_not_stringtypes(self):
        """
        A ``ConfigurationError`` is raised if any value in a fig application
        config's "links" list is not of ``types.StringTypes``.
        """
        config = {
            'postgres': {
                'environment': {'PG_ROOT_PASSWORD': 'clusterhq'},
                'image': 'sample/postgres',
                'ports': ['54320:5432'],
                'volumes': ['/var/lib/postgres'],
                'links': ['wordpress', 100],
            },
            'wordpress': {
                'image': 'sample/wordpress',
            }
        }
        parser = FigConfiguration(config)
        exception = self.assertRaises(
            ConfigurationError,
            parser.applications,
        )
        error_message = (
            "Application 'postgres' has a config error. "
            "'links' must be a list of application names with optional :alias."
        )
        self.assertEqual(exception.message, error_message)

    def test_invalid_fig_config_unknown_link(self):
        """
        A ``ConfigurationError`` is raised if in a fig application config, the
        "links" key contains an application name that cannot be mapped to any
        application present in the entire applications configuration.
        """
        config = {
            'postgres': {
                'environment': {'PG_ROOT_PASSWORD': 'clusterhq'},
                'image': 'sample/postgres',
                'ports': ['54320:5432'],
                'volumes': ['/var/lib/postgres'],
                'links': ['wordpress'],
            }
        }
        parser = FigConfiguration(config)
        exception = self.assertRaises(
            ConfigurationError,
            parser.applications,
        )
        error_message = (
            "Application 'postgres' has a config error. "
            "'links' value 'wordpress' could not be mapped to any "
            "application; application 'wordpress' does not exist."
        )
        self.assertEqual(exception.message, error_message)

    def test_fig_config_environment_list_item_empty_value(self):
        """
        An entry in a list of environment variables that is just a label is
        mapped to its label and a value of an empty unicode string.
        """
        config = {
            'postgres': {
                'environment': ['PGSQL_PORT_EXTERNAL=54320',
                                'PGSQL_USER_PASSWORD'],
                'image': 'sample/postgres',
                'ports': ['54320:5432'],
                'volumes': ['/var/lib/postgres'],
            }
        }
        parser = FigConfiguration(config)
        result = parser._parse_app_environment(
            'postgres',
            config['postgres']['environment']
        )
        expected = frozenset([
            (u'PGSQL_PORT_EXTERNAL', u'54320'),
            (u'PGSQL_USER_PASSWORD', u'')
        ])
        self.assertEqual(expected, result)

    def test_fig_config_environment_list_item_value(self):
        """
        A list of environment variables supplied in the form of LABEL=VALUE are
        parsed in to a ``frozenset`` mapping LABEL to VALUE.
        """
        config = {
            'postgres': {
                'environment': ['PGSQL_PORT_EXTERNAL=54320',
                                'PGSQL_USER_PASSWORD=admin'],
                'image': 'sample/postgres',
                'ports': ['54320:5432'],
                'volumes': ['/var/lib/postgres'],
            }
        }
        parser = FigConfiguration(config)
        result = parser._parse_app_environment(
            'postgres',
            config['postgres']['environment']
        )
        expected = frozenset([
            (u'PGSQL_PORT_EXTERNAL', u'54320'),
            (u'PGSQL_USER_PASSWORD', u'admin')
        ])
        self.assertEqual(expected, result)

    def test_invalid_fig_config_environment_list_item(self):
        """
        A ``ConfigurationError`` is raised if an entry in a list of
        'environment' values is not a string.
        """
        config = {
            'postgres': {
                'environment': [27014],
                'image': 'sample/postgres',
                'ports': ['54320:5432'],
                'volumes': ['/var/lib/postgres'],
                'links': ['wordpress'],
            }
        }
        parser = FigConfiguration(config)
        exception = self.assertRaises(
            ConfigurationError,
            parser.applications,
        )
        error_message = (
            "Application 'postgres' has a config error. "
            "'environment' value '27014' must be a string; got type 'int'."
        )
        self.assertEqual(exception.message, error_message)

    def test_invalid_fig_config_environment_format(self):
        """
        A ``ConfigurationError`` is raised if the "environments" key of a fig
        application config is not a dictionary or list.
        """
        config = {
            'postgres': {
                'environment': str('PG_ROOT_PASSWORD=clusterhq'),
                'image': 'sample/postgres',
                'ports': ['54320:5432'],
                'volumes': ['/var/lib/postgres'],
                'links': ['wordpress'],
            }
        }
        parser = FigConfiguration(config)
        exception = self.assertRaises(
            ConfigurationError,
            parser.applications,
        )
        error_message = (
            "Application 'postgres' has a config error. "
            "'environment' must be a dictionary or list; got type 'str'."
        )
        self.assertEqual(exception.message, error_message)

    def test_invalid_fig_config_env_not_stringtypes(self):
        """
        A ``ConfigurationError`` is raised if the "environment" dictionary
        in a fig application config contains a key whose value is not of
        ``types.StringTypes``.
        """
        config = {
            'postgres': {
                'environment': {'PG_ROOT_PASSWORD': ['a', 'b', 'c']},
                'image': 'sample/postgres',
                'ports': ['54320:5432'],
                'volumes': ['/var/lib/postgres'],
            }
        }
        parser = FigConfiguration(config)
        exception = self.assertRaises(
            ConfigurationError,
            parser.applications,
        )
        error_message = (
            "Application 'postgres' has a config error. "
            "'environment' value for 'PG_ROOT_PASSWORD' must be a string; "
            "got type 'list'."
        )
        self.assertEqual(exception.message, error_message)

    def test_invalid_fig_config_image_not_stringtypes(self):
        """
        A ``ConfigurationError`` is raised if the "image" key
        in a fig application config is a value not of
        ``types.StringTypes``.
        """
        config = {
            'postgres': {
                'environment': {'PG_ROOT_PASSWORD': 'clusterhq'},
                'image': ['clusterhq', 'postgres'],
                'ports': ['54320:5432'],
                'volumes': ['/var/lib/postgres'],
            }
        }
        parser = FigConfiguration(config)
        exception = self.assertRaises(
            ConfigurationError,
            parser.applications,
        )
        error_message = (
            "Application 'postgres' has a config error. "
            "'image' must be a string; got type 'list'."
        )
        self.assertEqual(exception.message, error_message)

    def test_invalid_fig_config_multiple_volumes(self):
        """
        A ``ConfigurationError`` is raised if the "volumes" key of a fig
        config is a list containing multiple entries. Only a maximum of
        one volume per container is currently supported.
        """
        config = {
            'postgres': {
                'environment': {'PG_ROOT_PASSWORD': 'clusterhq'},
                'image': 'sample/postgres',
                'ports': ['54320:5432'],
                'volumes': ['/var/lib/postgres', '/var/www/data'],
            }
        }
        parser = FigConfiguration(config)
        exception = self.assertRaises(
            ConfigurationError,
            parser.applications,
        )
        error_message = (
            "Application 'postgres' has a config error. "
            "Only one volume per application is supported at this time."
        )
        self.assertEqual(exception.message, error_message)

    def test_invalid_fig_config_volumes_not_list(self):
        """
        A ``ConfigurationError`` is raised if the "volumes" key of a fig
        compatible application config is not a list.
        """
        config = {
            'postgres': {
                'environment': {'PG_ROOT_PASSWORD': 'clusterhq'},
                'image': 'sample/postgres',
                'ports': ['54320:5432'],
                'volumes': str('/var/lib/postgres'),
            }
        }
        parser = FigConfiguration(config)
        exception = self.assertRaises(
            ConfigurationError,
            parser.applications,
        )
        error_message = (
            "Application 'postgres' has a config error. "
            "'volumes' must be a list; got type 'str'."
        )
        self.assertEqual(exception.message, error_message)

    def test_invalid_fig_config_volumes_not_stringtypes(self):
        """
        A ``ConfigurationError`` is raised if any value in a fig application's
        "volumes" list is not of ``types.StringTypes``.
        """
        config = {
            'postgres': {
                'environment': {'PG_ROOT_PASSWORD': 'clusterhq'},
                'image': 'sample/postgres',
                'ports': ['54320:5432'],
                'volumes': ['/var/lib/postgres', 1000],
            }
        }
        parser = FigConfiguration(config)
        exception = self.assertRaises(
            ConfigurationError,
            parser.applications,
        )
        error_message = (
            "Application 'postgres' has a config error. "
            "'volumes' values must be string; got type 'int'."
        )
        self.assertEqual(exception.message, error_message)


class ApplicationsFromConfigurationTests(SynchronousTestCase):
    def test_error_on_environment_var_not_stringtypes(self):
        """
        ``Configuration._applications.from_configuration`` raises a
        ``ConfigurationError`` if the application_configuration's
        ``u"environment"`` dictionary contains a key with a value
        that is not of ``types.StringTypes``.
        """
        config = {
            'mysql-hybridcluster': {
                'image': 'clusterhq/mysql',
                'environment': {
                    'MYSQL_PORT_3306_TCP': 3307,
                    'WP_ADMIN_USERNAME': "admin"
                }
            }
        }
        error_message = (
            "Application 'mysql-hybridcluster' has a config error. "
            "Environment variable 'MYSQL_PORT_3306_TCP' must be a string; "
            "got type 'int'.")
        parser = FlockerConfiguration(config)
        exception = self.assertRaises(ConfigurationError,
                                      parser._parse_environment_config,
                                      'mysql-hybridcluster',
                                      config['mysql-hybridcluster'])
        self.assertEqual(
            exception.message,
            error_message
        )

    def test_error_on_config_not_dict(self):
        """
        ``FlockerConfiguration.__init__`` raises a ``ConfigurationError``
        if the supplied configuration is not a ``dict``.
        """
        config = b'a string'
        e = self.assertRaises(ConfigurationError, FlockerConfiguration, config)
        self.assertEqual(
            e.message,
            "Application configuration must be a dictionary, got str."
        )

    def test_not_valid_on_application_not_dict(self):
        """
        ``FlockerConfiguration.is_valid_format`` returns ``False`` if the
        supplied configuration for a single application is not a ``dict``.
        """
        config = {'version': 1, 'applications': {'postgres': 'a string'}}
        parser = FlockerConfiguration(config)
        self.assertFalse(parser.is_valid_format())

    def test_not_valid_on_application_missing_image(self):
        """
        ``FlockerConfiguration.is_valid_format`` returns ``False`` if the
        supplied configuration for a single application does not contain the
        required "image" key.
        """
        config = {'version': 1, 'applications': {'postgres': {'build': '.'}}}
        parser = FlockerConfiguration(config)
        self.assertFalse(parser.is_valid_format())

    def test_error_on_environment_var_name_not_stringtypes(self):
        """
        ``Configuration._applications.from_configuration`` raises a
        ``ConfigurationError`` if the application_configuration's
        ``u"environment"`` dictionary contains a key that is not of
        ``types.StringTypes``.
        """
        config = {
            'mysql-hybridcluster': {
                'image': 'clusterhq/mysql',
                'environment': {
                    56: "test",
                }
            }
        }
        error_message = (
            "Application 'mysql-hybridcluster' has a config error. "
            "Environment variable name must be a string; "
            "got type 'int'.")
        parser = FlockerConfiguration(config)
        exception = self.assertRaises(ConfigurationError,
                                      parser._parse_environment_config,
                                      'mysql-hybridcluster',
                                      config['mysql-hybridcluster'])
        self.assertEqual(
            exception.message,
            error_message,
        )

    def test_error_on_environment_vars_not_dict(self):
        """
        ``Configuration._applications.from_configuration`` raises a
        ``ConfigurationError`` if the application_configuration's
        ``u"environment"`` key is not a dictionary.
        """
        config = {
            'mysql-hybridcluster': {
                'image': 'clusterhq/mysql',
                'environment': 'foobar'
            }
        }
        parser = FlockerConfiguration(config)
        exception = self.assertRaises(ConfigurationError,
                                      parser._parse_environment_config,
                                      'mysql-hybridcluster',
                                      config['mysql-hybridcluster'])
        self.assertEqual(
            "Application 'mysql-hybridcluster' has a config error. "
            "'environment' must be a dictionary of key/value pairs; "
            "got type 'unicode'.",
            exception.message
        )

    def test_error_on_missing_application_key(self):
        """
        ``Configuration.applications`` raises a
        ``ConfigurationError`` if the application_configuration does not
        contain an ``u"application"`` key.
        """
        config = dict()
        parser = FlockerConfiguration(config)
        exception = self.assertRaises(ConfigurationError,
                                      parser.applications)
        self.assertEqual(
            "Application configuration has an error. "
            "Missing 'applications' key.",
            exception.message
        )

    def test_error_on_missing_version_key(self):
        """
        ``Configuration.applications`` raises a
        ``ConfigurationError`` if the application_configuration does not
        contain an ``u"version"`` key.
        """
        config = dict(applications={})
        parser = FlockerConfiguration(config)
        exception = self.assertRaises(ConfigurationError,
                                      parser.applications)
        self.assertEqual(
            "Application configuration has an error. "
            "Missing 'version' key.",
            exception.message
        )

    def test_error_on_incorrect_version(self):
        """
        ``Configuration.applications`` raises a
        ``ConfigurationError`` if the version specified is not 1.
        """
        config = dict(applications={}, version=2)
        parser = FlockerConfiguration(config)
        exception = self.assertRaises(ConfigurationError,
                                      parser.applications)
        self.assertEqual(
            "Application configuration has an error. "
            "Incorrect version specified.",
            exception.message
        )

    def test_error_on_missing_application_attributes(self):
        """
        ``Configuration.applications`` raises a
        ``ConfigurationError`` if the application_configuration does not
        contain all the attributes of an ``Application`` record.
        """
        config = dict(applications={'mysql-hybridcluster': {}}, version=1)
        parser = FlockerConfiguration(config)
        exception = self.assertRaises(ConfigurationError,
                                      parser.applications)
        self.assertEqual(
            "Application 'mysql-hybridcluster' has a config error. "
            "Missing 'image' key.",
            exception.message
        )

    def test_error_on_extra_application_attributes(self):
        """
        ``Configuration.applications`` raises a
        ``ConfigurationError`` if the application_configuration contains
        unrecognised Application attribute names.
        """
        config = dict(
            version=1,
            applications={
                'mysql-hybridcluster': dict(image='foo/bar:baz', foo='bar',
                                            baz='quux')})
        parser = FlockerConfiguration(config)
        exception = self.assertRaises(ConfigurationError,
                                      parser.applications)
        self.assertEqual(
            "Application 'mysql-hybridcluster' has a config error. "
            "Unrecognised keys: baz, foo.",
            exception.message
        )

    def test_error_invalid_dockerimage_name(self):
        """
        ``Configuration.applications`` raises a
        ``ConfigurationError`` if the application_configuration uses invalid
        Docker image names.
        """
        invalid_docker_image_name = ':baz'
        config = dict(
            version=1,
            applications={'mysql-hybridcluster': dict(
                image=invalid_docker_image_name)})
        parser = FlockerConfiguration(config)
        exception = self.assertRaises(ConfigurationError,
                                      parser.applications)
        self.assertEqual(
            "Application 'mysql-hybridcluster' has a config error. "
            "Invalid Docker image name. "
            "Docker image names must have format 'repository[:tag]'. "
            "Found ':baz'.",
            exception.message
        )

    def test_environment_variables_none_if_missing(self):
        """
        ``Configuration._parse_environment_config`` returns ``None``
        if passed an application config that does not include an
        ``environment`` key.
        """
        config = {
            'mysql-hybridcluster': {
                'image': 'flocker/mysql'
            }
        }
        parser = FlockerConfiguration(config)
        self.assertIsNone(parser._parse_environment_config(
            'mysql-hybridcluster',
            config
        ))

    def test_dict_of_applications_environment(self):
        """
        ``Configuration._parse_environment_config`` returns a ``dict``
        of ``unicode`` values, one for each environment variable key in the
        supplied application configuration.
        """
        config = {
            'site-hybridcluster': {
                'image': 'flocker/wordpress:v1.0.0',
                'ports': [dict(internal=80, external=8080)],
                'environment': {
                    'MYSQL_PORT_3306_TCP': 'tcp://172.16.255.250:3306',
                    'WP_ADMIN_USERNAME': 'administrator',
                },
            }
        }
        parser = FlockerConfiguration(config)
        environment_vars = parser._parse_environment_config(
            'site-hybridcluster', config['site-hybridcluster'])
        expected_result = frozenset({
            'MYSQL_PORT_3306_TCP': u'tcp://172.16.255.250:3306',
            'WP_ADMIN_USERNAME': u'administrator',
        }.items())
        self.assertEqual(expected_result, environment_vars)

    def test_dict_of_applications(self):
        """
        ``Configuration.applications`` returns a ``dict``
        of ``Application`` instances, one for each application key in the
        supplied configuration.
        """
        config = dict(
            version=1,
            applications={
                'mysql-hybridcluster': dict(
                    image='flocker/mysql:v1.0.0',
                    volume={'mountpoint': b'/var/mysql/data'}
                ),
                'site-hybridcluster': {
                    'image': 'flocker/wordpress:v1.0.0',
                    'ports': [dict(internal=80, external=8080)],
                    'environment': {
                        'MYSQL_PORT_3306_TCP': 'tcp://172.16.255.250:3306',
                        'WP_ADMIN_USERNAME': 'administrator',
                    },
                }
            }
        )
        parser = FlockerConfiguration(config)
        applications = parser.applications()
        expected_applications = {
            'mysql-hybridcluster': Application(
                name='mysql-hybridcluster',
                image=DockerImage(repository='flocker/mysql', tag='v1.0.0'),
                ports=frozenset(),
                links=frozenset(),
                volume=AttachedVolume(
                    name='mysql-hybridcluster',
                    mountpoint=FilePath(b'/var/mysql/data'))),
            'site-hybridcluster': Application(
                name='site-hybridcluster',
                image=DockerImage(repository='flocker/wordpress',
                                  tag='v1.0.0'),
                ports=frozenset([Port(internal_port=80,
                                      external_port=8080)]),
                links=frozenset(),
                environment=frozenset({
                    'MYSQL_PORT_3306_TCP': 'tcp://172.16.255.250:3306',
                    'WP_ADMIN_USERNAME': 'administrator'
                }.items())
            ),
        }
        self.assertEqual(expected_applications, applications)

    def test_applications_hashable(self):
        """
        `Application` instances returned by
        ``Configuration.applications`` are hashable
        and a `frozenset` of `Application` instances can be created.
        """
        config = dict(
            version=1,
            applications={
                'mysql-hybridcluster': {
                    'image': 'clusterhq/mysql:v1.0.0',
                    'ports': [dict(internal=3306, external=3306)],
                    'volume': {'mountpoint': b'/var/lib/mysql'},
                },
                'site-hybridcluster': {
                    'image': 'clusterhq/wordpress:v1.0.0',
                    'ports': [dict(internal=80, external=8080)],
                    'links': [{'alias': 'mysql', 'local_port': 3306,
                               'remote_port': 3306}],
                    'volume': {'mountpoint': b'/var/www/data'},
                    'environment': {
                        'MYSQL_PORT_3306_TCP': 'tcp://172.16.255.250:3306'
                    },
                }
            }
        )
        parser = FlockerConfiguration(config)
        applications = parser.applications()
        expected_applications = {
            'mysql-hybridcluster': Application(
                name='mysql-hybridcluster',
                image=DockerImage(repository='clusterhq/mysql', tag='v1.0.0'),
                ports=frozenset([Port(internal_port=3306,
                                      external_port=3306)]),
                links=frozenset(),
                volume=AttachedVolume(name='mysql-hybridcluster',
                                      mountpoint=FilePath(b'/var/lib/mysql'))
            ),
            'site-hybridcluster': Application(
                name='site-hybridcluster',
                image=DockerImage(repository='clusterhq/wordpress',
                                  tag='v1.0.0'),
                ports=frozenset([Port(internal_port=80, external_port=8080)]),
                links=frozenset([Link(local_port=3306, remote_port=3306,
                                      alias=u'mysql')]),
                volume=AttachedVolume(name='site-hybridcluster',
                                      mountpoint=FilePath(b'/var/www/data')),
                environment=frozenset({
                    'MYSQL_PORT_3306_TCP': 'tcp://172.16.255.250:3306'
                }.items())
            )
        }
        applications_set = frozenset(applications.values())
        expected_applications_set = frozenset(expected_applications.values())
        self.assertEqual(applications_set, expected_applications_set)

    def test_ports_missing_internal(self):
        """
        ``Configuration.applications`` raises a
        ``ConfigurationError`` if the application_configuration has a port
        entry that is missing the internal port.
        """
        config = dict(
            version=1,
            applications={'mysql-hybridcluster': dict(
                image='busybox',
                ports=[{'external': 90}],
                )})
        parser = FlockerConfiguration(config)
        exception = self.assertRaises(ConfigurationError,
                                      parser.applications)
        self.assertEqual(
            "Application 'mysql-hybridcluster' has a config error. "
            "Invalid ports specification. Missing internal port.",
            exception.message
        )

    def test_ports_missing_external(self):
        """
        ``Configuration.applications`` raises a
        ``ConfigurationError`` if the application_configuration has a port
        entry that is missing the internal port.
        """
        config = dict(
            version=1,
            applications={'mysql-hybridcluster': dict(
                image='busybox',
                ports=[{'internal': 90}],
                )})
        parser = FlockerConfiguration(config)
        exception = self.assertRaises(ConfigurationError,
                                      parser.applications)
        self.assertEqual(
            "Application 'mysql-hybridcluster' has a config error. "
            "Invalid ports specification. Missing external port.",
            exception.message
        )

    def test_ports_extra_keys(self):
        """
        ``Configuration.applications`` raises a
        ``ConfigurationError`` if the application_configuration has a port
        entry that has extra keys.
        """
        config = dict(
            version=1,
            applications={'mysql-hybridcluster': dict(
                image='busybox',
                ports=[{'internal': 90, 'external': 40,
                        'foo': 5, 'bar': 'six'}],
                )})
        parser = FlockerConfiguration(config)
        exception = self.assertRaises(ConfigurationError,
                                      parser.applications)
        self.assertEqual(
            "Application 'mysql-hybridcluster' has a config error. "
            "Invalid ports specification. Unrecognised keys: bar, foo.",
            exception.message
        )

    def test_links_missing_local_port(self):
        """
        ``Configuration.applications`` raises a
        ``ConfigurationError`` if the application_configuration has a link
        entry that is missing the remote port.
        """
        config = dict(
            version=1,
            applications={'mysql-hybridcluster': dict(
                image='busybox',
                links=[{'remote_port': 90,
                        'alias': 'mysql'}],
                )})
        parser = FlockerConfiguration(config)
        exception = self.assertRaises(ConfigurationError,
                                      parser.applications)
        self.assertEqual(
            "Application 'mysql-hybridcluster' has a config error. "
            "Invalid links specification. Missing local port.",
            exception.message
        )

    def test_links_missing_remote_port(self):
        """
        ``Configuration.applications`` raises a
        ``ConfigurationError`` if the application_configuration has a link
        entry that is missing the local port.
        """
        config = dict(
            version=1,
            applications={'mysql-hybridcluster': dict(
                image='busybox',
                links=[{'local_port': 90,
                        'alias': 'mysql'}],
                )})
        parser = FlockerConfiguration(config)
        exception = self.assertRaises(ConfigurationError,
                                      parser.applications)
        self.assertEqual(
            "Application 'mysql-hybridcluster' has a config error. "
            "Invalid links specification. Missing remote port.",
            exception.message
        )

    def test_links_missing_alias(self):
        """
        ``Configuration.applications`` raises a
        ``ConfigurationError`` if the application_configuration has a link
        entry that is missing the alias.
        """
        config = dict(
            version=1,
            applications={'mysql-hybridcluster': dict(
                image='busybox',
                links=[{'local_port': 90, 'remote_port': 100}],
                )})
        parser = FlockerConfiguration(config)
        exception = self.assertRaises(ConfigurationError,
                                      parser.applications)
        self.assertEqual(
            "Application 'mysql-hybridcluster' has a config error. "
            "Invalid links specification. Missing alias.",
            exception.message
        )

    def test_links_extra_keys(self):
        """
        ``Configuration.applications`` raises a
        ``ConfigurationError`` if the application_configuration has a link
        entry that has extra keys.
        """
        config = dict(
            version=1,
            applications={'mysql-hybridcluster': dict(
                image='busybox',
                links=[{'remote_port': 90, 'local_port': 40, 'alias': 'other',
                        'foo': 5, 'bar': 'six'}],
                )})
        parser = FlockerConfiguration(config)
        exception = self.assertRaises(ConfigurationError,
                                      parser.applications)
        self.assertEqual(
            "Application 'mysql-hybridcluster' has a config error. "
            "Invalid links specification. Unrecognised keys: bar, foo.",
            exception.message
        )

    def test_error_on_link_alias_not_stringtypes(self):
        """
        ``Configuration._parse_link_configuration`` raises a
        ``ConfigurationError`` if a configured link has an alias that is not of
        ``types.StringTypes``.
        """
        links = [
            {
                'alias': ['not', 'a', 'string'],
                'local_port': 1234,
                'remote_port': 5678,
            }
        ]
        config = dict()
        parser = FlockerConfiguration(config)
        exception = self.assertRaises(ConfigurationError,
                                      parser._parse_link_configuration,
                                      'mysql-hybridcluster',
                                      links)
        self.assertEqual(
            "Application 'mysql-hybridcluster' has a config error. "
            "Link alias must be a string; got type 'list'.",
            exception.message
        )

    def test_error_on_link_local_port_not_int(self):
        """
        ``Configuration._parse_link_configuration`` raises a
        ``ConfigurationError`` if a configured link has an local port that is
        not of type ``int``.
        """
        links = [
            {
                'alias': "some-service",
                'local_port': 1.2,
                'remote_port': 5678,
            }
        ]
        config = dict()
        parser = FlockerConfiguration(config)
        exception = self.assertRaises(ConfigurationError,
                                      parser._parse_link_configuration,
                                      'mysql-hybridcluster',
                                      links)
        self.assertEqual(
            "Application 'mysql-hybridcluster' has a config error. "
            "Link's local port must be an int; got type 'float'.",
            exception.message
        )

    def test_error_on_link_remote_port_not_int(self):
        """
        ``Configuration._parse_link_configuration`` raises a
        ``ConfigurationError`` if a configured link has an remote port that is
        not of type ``int``.
        """
        links = [
            {
                'alias': "some-service",
                'local_port': 1234,
                'remote_port': 56.78,
            }
        ]
        config = dict()
        parser = FlockerConfiguration(config)
        exception = self.assertRaises(ConfigurationError,
                                      parser._parse_link_configuration,
                                      'mysql-hybridcluster',
                                      links)
        self.assertEqual(
            "Application 'mysql-hybridcluster' has a config error. "
            "Link's remote port must be an int; got type 'float'.",
            exception.message
        )

    def test_error_on_links_not_list(self):
        """
        ``Configuration._parse_link_configuration`` raises a
        ``ConfigurationError`` if the application_configuration's
        ``u"links"`` key is not a dictionary.
        """
        config = dict()
        parser = FlockerConfiguration(config)
        exception = self.assertRaises(ConfigurationError,
                                      parser._parse_link_configuration,
                                      'mysql-hybridcluster',
                                      u'not-a-list')
        self.assertEqual(
            "Application 'mysql-hybridcluster' has a config error. "
            "'links' must be a list of dictionaries; "
            "got type 'unicode'.",
            exception.message
        )

    def test_error_on_link_not_dictonary(self):
        """
        ``Configuration._parse_link_configuration`` raises a
        ``ConfigurationError`` if a link is not a dictionary.
        """
        config = dict()
        parser = FlockerConfiguration(config)
        exception = self.assertRaises(ConfigurationError,
                                      parser._parse_link_configuration,
                                      'mysql-hybridcluster',
                                      [u'not-a-dictionary'])
        self.assertEqual(
            "Application 'mysql-hybridcluster' has a config error. "
            "Link must be a dictionary; "
            "got type 'unicode'.",
            exception.message
        )

    def test_error_on_volume_extra_keys(self):
        """
        ``Configuration.applications`` raises a
        ``ConfigurationError`` error if the volume dictionary contains
        extra keys.
        """
        config = dict(
            version=1,
            applications={'mysql-hybridcluster': dict(
                image='busybox',
                volume={'mountpoint': b'/var/mysql/data',
                        'bar': 'baz',
                        'foo': 215},
            )}
        )
        parser = FlockerConfiguration(config)
        exception = self.assertRaises(ConfigurationError,
                                      parser.applications)
        self.assertEqual(
            "Application 'mysql-hybridcluster' has a config error. "
            "Invalid volume specification. Unrecognised keys: bar, foo.",
            exception.message
        )

    def test_error_on_volume_missing_mountpoint(self):
        """
        ``Configuration.applications`` raises a
        ``ConfigurationError`` error if the volume key does not
        contain a mountpoint.
        """
        config = dict(
            version=1,
            applications={'mysql-hybridcluster': dict(
                image='busybox',
                volume={},
            )}
        )
        parser = FlockerConfiguration(config)
        exception = self.assertRaises(ConfigurationError,
                                      parser.applications)
        self.assertEqual(
            "Application 'mysql-hybridcluster' has a config error. "
            "Invalid volume specification. Missing mountpoint.",
            exception.message
        )

    def test_error_on_volume_invalid_mountpoint(self):
        """
        ``Configuration.applications`` raises a
        ``ConfigurationError`` error if the specified volume mountpoint is
        not a valid absolute path.
        """
        config = dict(
            version=1,
            applications={'mysql-hybridcluster': dict(
                image='busybox',
                volume={'mountpoint': b'./.././var//'},
            )}
        )
        parser = FlockerConfiguration(config)
        exception = self.assertRaises(ConfigurationError,
                                      parser.applications)
        self.assertEqual(
            "Application 'mysql-hybridcluster' has a config error. "
            "Invalid volume specification. Mountpoint \"./.././var//\" is not "
            "an absolute path.",
            exception.message
        )

    def test_error_on_volume_mountpoint_not_ascii(self):
        """
        ``Configuration.applications`` raises a
        ``ConfigurationError`` error if the specified volume mountpoint is
        not a byte string.
        """
        mountpoint_unicode = u'\u2603'
        config = dict(
            version=1,
            applications={'mysql-hybridcluster': dict(
                image='busybox',
                volume={'mountpoint': mountpoint_unicode},
            )}
        )
        parser = FlockerConfiguration(config)
        exception = self.assertRaises(ConfigurationError,
                                      parser.applications)
        self.assertEqual(
            "Application 'mysql-hybridcluster' has a config error. "
            "Invalid volume specification. Mountpoint \"{mount}\" contains "
            "non-ASCII (unsupported).".format(mount=mountpoint_unicode),
            exception.message
        )

    def test_error_on_invalid_volume_yaml(self):
        """
        ``Configuration.applications`` raises a
        ``ConfigurationError`` if the volume key is not a dictionary.
        """
        config = dict(
            version=1,
            applications={'mysql-hybridcluster': dict(
                image='busybox',
                volume='a random string',
            )}
        )
        parser = FlockerConfiguration(config)
        exception = self.assertRaises(ConfigurationError,
                                      parser.applications)
        self.assertEqual(
            "Application 'mysql-hybridcluster' has a config error. "
            "Invalid volume specification. Unexpected value: a random string",
            exception.message
        )


class DeploymentFromConfigurationTests(SynchronousTestCase):
    """
    Tests for ``Configuration._deployment_from_configuration``.
    """
    def test_error_on_missing_nodes_key(self):
        """
        ``Configuration._deployment_from_config`` raises a
        ``ConfigurationError`` if the deployment_configuration does not
        contain an ``u"nodes"`` key.
        """
        exception = self.assertRaises(ConfigurationError,
                                      deployment_from_configuration,
                                      {}, set())
        self.assertEqual(
            "Deployment configuration has an error. Missing 'nodes' key.",
            exception.message
        )

    def test_error_on_missing_version_key(self):
        """
        ``Configuration._deployment_from_config`` raises a
        ``ConfigurationError`` if the deployment_configuration does not
        contain an ``u"version"`` key.
        """
        config = dict(nodes={})
        exception = self.assertRaises(ConfigurationError,
                                      deployment_from_configuration,
                                      config, set())
        self.assertEqual(
            "Deployment configuration has an error. Missing 'version' key.",
            exception.message
        )

    def test_error_on_incorrect_version(self):
        """
        ``Configuration._deployment_from_config`` raises a
        ``ConfigurationError`` if the version specified is not 1.
        """
        config = dict(nodes={}, version=2)
        exception = self.assertRaises(ConfigurationError,
                                      deployment_from_configuration,
                                      config, set())
        self.assertEqual(
            "Deployment configuration has an error. "
            "Incorrect version specified.",
            exception.message
        )

    def test_error_on_non_list_applications(self):
        """
        ``_deployment_from_config`` raises a ``ValueError`` if the
        deployment_configuration contains application values not in the form of
        a list.
        """
        exception = self.assertRaises(
            ConfigurationError,
            deployment_from_configuration,
            dict(version=1, nodes={'node1.example.com': None}),
            set()
        )
        self.assertEqual(
            'Node node1.example.com has a config error. '
            'Wrong value type: NoneType. '
            'Should be list.',
            exception.message
        )

    def test_error_on_unrecognized_application_name(self):
        """
        ``_deployment_from_config`` raises a ``ValueError`` if the
        deployment_configuration refers to a non-existent application.
        """
        applications = {
            'mysql-hybridcluster': Application(
                name='mysql-hybridcluster',
                image=Application(
                    name='mysql-hybridcluster',
                    image=DockerImage(repository='flocker/mysql',
                                      tag='v1.0.0'))
            )
        }
        exception = self.assertRaises(
            ConfigurationError,
            deployment_from_configuration,
            dict(
                version=1,
                nodes={'node1.example.com': ['site-hybridcluster']}),
            applications
        )
        self.assertEqual(
            'Node node1.example.com has a config error. '
            'Unrecognised application name: site-hybridcluster.',
            exception.message
        )

    def test_set_on_success(self):
        """
        ``_deployment_from_config`` returns a set of ``Node`` objects. One for
        each key in the supplied nodes dictionary.
        """
        applications = {
            'mysql-hybridcluster': Application(
                name='mysql-hybridcluster',
                image=Application(
                    name='mysql-hybridcluster',
                    image=DockerImage(repository='flocker/mysql',
                                      tag='v1.0.0'))
            )
        }
        result = deployment_from_configuration(
            dict(
                version=1,
                nodes={'node1.example.com': ['mysql-hybridcluster']}),
            applications
        )

        expected = set([
            Node(
                hostname='node1.example.com',
                applications=frozenset(applications.values())
            )
        ])

        self.assertEqual(expected, result)


class ModelFromConfigurationTests(SynchronousTestCase):
    """
    Tests for ``Configuration.model_from_configuration``.
    """
    def test_model_from_configuration_empty(self):
        """
        ``Configuration.model_from_configuration`` returns an empty
        ``Deployment`` object if supplied with empty configurations.
        """
        application_configuration = {}
        deployment_configuration = {'nodes': {}, 'version': 1}
        result = model_from_configuration(
            application_configuration, deployment_configuration)
        expected_result = Deployment(nodes=frozenset())
        self.assertEqual(expected_result, result)

    def test_model_from_configuration(self):
        """
        ``Configuration.model_from_configuration`` returns a
        ``Deployment`` object with ``Nodes`` for each supplied node key.
        """
        application_configuration = {
            'version': 1,
            'applications': {
                'mysql-hybridcluster': {'image': 'flocker/mysql:v1.2.3'},
                'site-hybridcluster': {'image': 'flocker/nginx:v1.2.3'}
            }
        }
        deployment_configuration = {
            'version': 1,
            'nodes': {
                'node1.example.com': ['mysql-hybridcluster'],
                'node2.example.com': ['site-hybridcluster'],
            }
        }
        config = FlockerConfiguration(application_configuration)
        applications = config.applications()
        result = model_from_configuration(
            applications, deployment_configuration)
        expected_result = Deployment(
            nodes=frozenset([
                Node(
                    hostname='node1.example.com',
                    applications=frozenset([
                        Application(
                            name='mysql-hybridcluster',
                            image=DockerImage(
                                repository='flocker/mysql',
                                tag='v1.2.3'
                            ),
                            ports=frozenset(),
                            links=frozenset(),
                        ),
                    ])
                ),
                Node(
                    hostname='node2.example.com',
                    applications=frozenset([
                        Application(
                            name='site-hybridcluster',
                            image=DockerImage(
                                repository='flocker/nginx',
                                tag='v1.2.3'
                            ),
                            ports=frozenset(),
                            links=frozenset(),
                        ),
                    ])
                )
            ])
        )
        self.assertEqual(expected_result, result)


class MarshalConfigurationTests(SynchronousTestCase):
    """
    Tests for ``Configuration.marshal_configuration``.
    """
    def test_no_applications(self):
        """
        A dict with a version and empty applications list are returned if no
        applications are supplied.
        """
        result = marshal_configuration(NodeState(running=[], not_running=[]))
        expected = {
            'applications': {},
            'used_ports': [],
            'version': 1,
        }
        self.assertEqual(expected, result)

    def test_one_application(self):
        """
        A dictionary of application name -> image is produced where the
        ``marshal_configuration`` method is called with state containing only
        one application.
        """
        applications = [
            Application(
                name='mysql-hybridcluster',
                image=DockerImage(repository='flocker/mysql',
                                  tag='v1.0.0')
            )
        ]
        result = marshal_configuration(
            NodeState(running=applications, not_running=[]))
        expected = {
            'used_ports': [],
            'applications': {
                'mysql-hybridcluster': {'image': u'flocker/mysql:v1.0.0'}
            },
            'version': 1,
        }
        self.assertEqual(expected, result)

    def test_multiple_applications(self):
        """
        The dictionary includes a representation of each supplied application.
        """
        applications = [
            Application(
                name='mysql-hybridcluster',
                image=DockerImage(repository='flocker/mysql',
                                  tag='v1.0.0')
            ),
            Application(
                name='site-hybridcluster',
                image=DockerImage(repository='flocker/wordpress',
                                  tag='v1.0.0')
            )
        ]
        result = marshal_configuration(
            NodeState(running=applications, not_running=[]))
        expected = {
            'used_ports': [],
            'applications': {
                'site-hybridcluster': {
                    'image': u'flocker/wordpress:v1.0.0'
                },
                'mysql-hybridcluster': {'image': u'flocker/mysql:v1.0.0'}
            },
            'version': 1,
        }
        self.assertEqual(expected, result)

    def test_application_ports(self):
        """
        The dictionary includes a representation of each supplied application,
        including exposed internal and external ports where the
        ``Application`` specifies these.
        """
        applications = [
            Application(
                name='site-hybridcluster',
                image=DockerImage(repository='flocker/wordpress',
                                  tag='v1.0.0'),
                ports=frozenset([Port(internal_port=80,
                                      external_port=8080)])
            )
        ]
        result = marshal_configuration(
            NodeState(running=applications, not_running=[]))
        expected = {
            'used_ports': [],
            'applications': {
                'site-hybridcluster': {
                    'image': u'flocker/wordpress:v1.0.0',
                    'ports': [{'internal': 80, 'external': 8080}]
                },
            },
            'version': 1,
        }
        self.assertEqual(expected, result)

    def test_application_links(self):
        """
        The dictionary includes a representation of each supplied application,
        including links to other application when the ``Application`` specifies
        these.
        """
        applications = [
            Application(
                name='site-hybridcluster',
                image=DockerImage(repository='flocker/wordpress',
                                  tag='v1.0.0'),
                links=frozenset([Link(local_port=3306,
                                      remote_port=63306,
                                      alias='mysql')])
            )
        ]
        result = marshal_configuration(
            NodeState(running=applications, not_running=[]))
        expected = {
            'used_ports': [],
            'applications': {
                'site-hybridcluster': {
                    'image': u'flocker/wordpress:v1.0.0',
                    'links': [{'local_port': 3306, 'remote_port': 63306,
                               'alias': 'mysql'}]
                },
            },
            'version': 1
        }
        self.assertEqual(expected, result)

    def test_application_with_volume_includes_mountpoint(self):
        """
        If the supplied applications have a volume, the resulting yaml will
        also include the volume mountpoint.
        """
        applications = [
            Application(
                name='mysql-hybridcluster',
                image=DockerImage(repository='flocker/mysql', tag='v1.0.0'),
                ports=frozenset(),
                volume=AttachedVolume(
                    name='mysql-hybridcluster',
                    mountpoint=FilePath(b'/var/mysql/data'))
            ),
            Application(
                name='site-hybridcluster',
                image=DockerImage(repository='flocker/wordpress',
                                  tag='v1.0.0'),
                ports=frozenset([Port(internal_port=80,
                                      external_port=8080)])
            )
        ]
        result = marshal_configuration(
            NodeState(running=applications, not_running=[]))
        expected = {
            'used_ports': [],
            'applications': {
                'site-hybridcluster': {
                    'image': u'flocker/wordpress:v1.0.0',
                    'ports': [{'internal': 80, 'external': 8080}]
                },
                'mysql-hybridcluster': {
                    'volume': {'mountpoint': b'/var/mysql/data'},
                    'image': u'flocker/mysql:v1.0.0'
                }
            },
            'version': 1,
        }
        self.assertEqual(expected, result)

    def test_running_and_not_running_applications(self):
        """
        Both the ``running`` and ``not_running`` application lists are
        marshalled into the result.
        """
        running = Application(
            name='mysql-hybridcluster',
            image=DockerImage(repository='flocker/mysql', tag='v1.0.0'),
            ports=frozenset(),
            volume=AttachedVolume(
                name='mysql-hybridcluster',
                mountpoint=FilePath(b'/var/mysql/data')
            ),
        )

        not_running = Application(
            name='site-hybridcluster',
            image=DockerImage(repository='flocker/wordpress',
                              tag='v1.0.0'),
            ports=frozenset([Port(internal_port=80, external_port=8080)])
        )

        result = marshal_configuration(
            NodeState(running=[running], not_running=[not_running]))

        expected = {
            'used_ports': [],
            'applications': {
                'site-hybridcluster': {
                    'image': u'flocker/wordpress:v1.0.0',
                    'ports': [{'internal': 80, 'external': 8080}]
                },
                'mysql-hybridcluster': {
                    'volume': {'mountpoint': b'/var/mysql/data'},
                    'image': u'flocker/mysql:v1.0.0'
                }
            },
            'version': 1
        }
        self.assertEqual(expected, result)

    def test_used_ports(self):
        """
        The ports in ``NodeState.used_ports`` are included in the result of
        ``marshal_configuration``.
        """
        used_ports = frozenset({1, 20, 250, 15020, 65000})
        state = NodeState(running=[], not_running=[], used_ports=used_ports)
        expected = {
            'used_ports': sorted(used_ports),
            'applications': {},
            'version': 1,
        }
        self.assertEqual(
            expected,
            marshal_configuration(state)
        )

    def test_able_to_unmarshal_configuration(self):
        """
        ``Configuration._applications_from_configuration`` can load the output
        of ``marshal_configuration`` into ``Application``\ s.
        """
        applications = [
            Application(
                name='mysql-hybridcluster',
                image=DockerImage(repository='flocker/mysql', tag='v1.0.0'),
                ports=frozenset(),
                links=frozenset(),
                volume=AttachedVolume(
                    name='mysql-hybridcluster',
                    mountpoint=FilePath(b"/var/lib/data"))
            ),
            Application(
                name='site-hybridcluster',
                image=DockerImage(repository='flocker/wordpress',
                                  tag='v1.0.0'),
                ports=frozenset([Port(internal_port=80,
                                      external_port=8080)]),
                links=frozenset([Link(local_port=3306,
                                      remote_port=63306,
                                      alias='mysql')]),
            )
        ]
        expected_applications = {
            b'mysql-hybridcluster': Application(
                name=b'mysql-hybridcluster',
                image=DockerImage(repository='flocker/mysql',
                                  tag='v1.0.0'),
                ports=frozenset(),
                links=frozenset(),
                volume=AttachedVolume(
                    name=b'mysql-hybridcluster',
                    mountpoint=FilePath(b"/var/lib/data")
                )
            ),
            b'site-hybridcluster': Application(
                name=b'site-hybridcluster',
                image=DockerImage(repository='flocker/wordpress',
                                  tag='v1.0.0'),
                ports=frozenset([Port(internal_port=80,
                                      external_port=8080)]),
                links=frozenset([Link(local_port=3306,
                                      remote_port=63306,
                                      alias='mysql')]),
            )
        }
        result = marshal_configuration(
            NodeState(running=applications, not_running=[]))
        config = FlockerConfiguration(result)
        apps = config.applications()
        self.assertEqual(expected_applications, apps)


class CurrentFromConfigurationTests(SynchronousTestCase):
    """
    Tests for ``current_from_configuration``.
    """
    def test_deployment(self):
        """
        ``current_from_configuration`` creates a ``Deployment`` object with
        the appropriate configuration for each included node.
        """
        config = {'example.com': {
            'applications': {
                'site-hybridcluster': {
                    'image': 'unknown',
                },
                'mysql-hybridcluster': {
                    'image': 'unknown',
                }
            },
            'version': 1
        }}
        expected = Deployment(nodes=frozenset([
            Node(hostname='example.com', applications=frozenset([
                Application(
                    name='mysql-hybridcluster',
                    image=DockerImage.from_string('unknown'),
                    ports=frozenset(),
                    links=frozenset(),
                ),
                Application(
                    name='site-hybridcluster',
                    image=DockerImage.from_string('unknown'),
                    ports=frozenset(),
                    links=frozenset(),
                )]))]))
        self.assertEqual(expected,
                         current_from_configuration(config))

    def test_multiple_hosts(self):
        """
        ``current_from_configuration`` can handle information from multiple
        hosts.
        """
        config = {
            'example.com': {
                'applications': {
                    'site-hybridcluster': {
                        'image': 'unknown',
                    },
                },
                'version': 1,
            },
            'example.net': {
                'applications': {
                    'mysql-hybridcluster': {
                        'image': 'unknown',
                    }
                },
                'version': 1,
            },
        }
        expected = Deployment(nodes=frozenset([
            Node(hostname='example.com', applications=frozenset([
                Application(
                    name='site-hybridcluster',
                    image=DockerImage.from_string('unknown'),
                    ports=frozenset(),
                    links=frozenset(),
                )])),
            Node(hostname='example.net', applications=frozenset([
                Application(
                    name='mysql-hybridcluster',
                    image=DockerImage.from_string('unknown'),
                    ports=frozenset(),
                    links=frozenset(),
                )]))]))
        self.assertEqual(expected,
                         current_from_configuration(config))

    def test_error_on_mountpoint_none(self):
        """
        ``current_from_configuration`` rejects ``None`` for volume
        mountpoints, raising a ``ConfigurationError``.
        """
        config = {'example.com': {
            'applications': {
                'mysql-hybridcluster': {
                    'image': 'unknown',
                    'volume': {'mountpoint': None},
                }
            },
            'version': 1
        }}

        e = self.assertRaises(ConfigurationError, current_from_configuration,
                              config)
        expected = (
            "Application 'mysql-hybridcluster' has a config error. Invalid "
            "volume specification. Mountpoint \"None\" contains non-ASCII "
            "(unsupported)."
        )
        self.assertEqual(e.message, expected)
