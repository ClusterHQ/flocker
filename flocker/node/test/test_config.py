# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.node._config``.
"""

from __future__ import unicode_literals, absolute_import

from twisted.trial.unittest import SynchronousTestCase
from .._config import ConfigurationError, Configuration
from .._model import Application, DockerImage, Deployment, Node
from ..gear import PortMap


class ApplicationsFromConfigurationTests(SynchronousTestCase):
    """
    Tests for ``Configuration._applications_from_configuration``.
    """
    def test_error_on_missing_application_key(self):
        """
        ``Configuration._applications_from_configuration`` raises a
        ``ConfigurationError`` if the application_configuration does not
        contain an ``u"application"`` key.
        """
        parser = Configuration()
        exception = self.assertRaises(ConfigurationError,
                                      parser._applications_from_configuration,
                                      {})
        self.assertEqual(
            "Application configuration has an error. "
            "Missing 'applications' key.",
            exception.message
        )

    def test_error_on_missing_version_key(self):
        """
        ``Configuration._applications_from_configuration`` raises a
        ``ConfigurationError`` if the application_configuration does not
        contain an ``u"version"`` key.
        """
        config = dict(applications={})
        parser = Configuration()
        exception = self.assertRaises(ConfigurationError,
                                      parser._applications_from_configuration,
                                      config)
        self.assertEqual(
            "Application configuration has an error. "
            "Missing 'version' key.",
            exception.message
        )

    def test_error_on_incorrect_version(self):
        """
        ``Configuration._applications_from_configuration`` raises a
        ``ConfigurationError`` if the version specified is not 1.
        """
        config = dict(applications={}, version=2)
        parser = Configuration()
        exception = self.assertRaises(ConfigurationError,
                                      parser._applications_from_configuration,
                                      config)
        self.assertEqual(
            "Application configuration has an error. "
            "Incorrect version specified.",
            exception.message
        )

    def test_error_on_missing_application_attributes(self):
        """
        ``Configuration._applications_from_configuration`` raises a
        ``ConfigurationError`` if the application_configuration does not
        contain all the attributes of an ``Application`` record.
        """
        config = dict(applications={'mysql-hybridcluster': {}}, version=1)
        parser = Configuration()
        exception = self.assertRaises(ConfigurationError,
                                      parser._applications_from_configuration,
                                      config)
        self.assertEqual(
            "Application 'mysql-hybridcluster' has a config error. "
            "Missing value for 'image'.",
            exception.message
        )

    def test_error_on_extra_application_attributes(self):
        """
        ``Configuration._applications_from_configuration`` raises a
        ``ConfigurationError`` if the application_configuration contains
        unrecognised Application attribute names.
        """
        config = dict(
            version=1,
            applications={
                'mysql-hybridcluster': dict(image='foo/bar:baz', foo='bar',
                                            baz='quux')})
        parser = Configuration()
        exception = self.assertRaises(ConfigurationError,
                                      parser._applications_from_configuration,
                                      config)
        self.assertEqual(
            "Application 'mysql-hybridcluster' has a config error. "
            "Unrecognised keys: foo, baz.",
            exception.message
        )

    def test_error_invalid_dockerimage_name(self):
        """
        ``Configuration._applications_from_configuration`` raises a
        ``ConfigurationError`` if the application_configuration uses invalid
        Docker image names.
        """
        invalid_docker_image_name = ':baz'
        config = dict(
            version=1,
            applications={'mysql-hybridcluster': dict(
                image=invalid_docker_image_name)})
        parser = Configuration()
        exception = self.assertRaises(ConfigurationError,
                                      parser._applications_from_configuration,
                                      config)
        self.assertEqual(
            "Application 'mysql-hybridcluster' has a config error. "
            "Invalid Docker image name. "
            "Docker image names must have format 'repository[:tag]'. "
            "Found ':baz'.",
            exception.message
        )

    def test_dict_of_applications(self):
        """
        ``Configuration._applications_from_configuration`` returns a ``dict``
        of ``Application`` instances, one for each application key in the
        supplied configuration.
        """
        config = dict(
            version=1,
            applications={
                'mysql-hybridcluster': dict(image='flocker/mysql:v1.0.0'),
                'site-hybridcluster': {
                    'image': 'flocker/wordpress:v1.0.0',
                    'ports': [dict(internal=80, external=8080)]
                }
            }
        )
        parser = Configuration()
        applications = parser._applications_from_configuration(config)
        expected_applications = {
            'mysql-hybridcluster': Application(
                name='mysql-hybridcluster',
                image=DockerImage(repository='flocker/mysql', tag='v1.0.0'),
                ports=frozenset()),
            'site-hybridcluster': Application(
                name='site-hybridcluster',
                image=DockerImage(repository='flocker/wordpress',
                                  tag='v1.0.0'),
                ports=frozenset([PortMap(internal_port=80, external_port=8080)]))
        }

        self.assertEqual(expected_applications, applications)


    def test_ports_missing_internal(self):
        """
        ``Configuration._applications_from_configuration`` raises a
        ``ConfigurationError`` if the application_configuration has a port entry
        that is missing the internal port.
        """
        config = dict(
            version=1,
            applications={'mysql-hybridcluster': dict(
                image='busybox',
                ports=[{'external': 90}],
                )})
        parser = Configuration()
        exception = self.assertRaises(ConfigurationError,
                                      parser._applications_from_configuration,
                                      config)
        self.assertEqual(
            "Application 'mysql-hybridcluster' has a config error. "
            "Invalid ports specification. Missing internal port.",
            exception.message
        )

    def test_ports_missing_external(self):
        """
        ``Configuration._applications_from_configuration`` raises a
        ``ConfigurationError`` if the application_configuration has a port entry
        that is missing the internal port.
        """
        config = dict(
            version=1,
            applications={'mysql-hybridcluster': dict(
                image='busybox',
                ports=[{'internal': 90}],
                )})
        parser = Configuration()
        exception = self.assertRaises(ConfigurationError,
                                      parser._applications_from_configuration,
                                      config)
        self.assertEqual(
            "Application 'mysql-hybridcluster' has a config error. "
            "Invalid ports specification. Missing external port.",
            exception.message
        )

    def test_ports_extra_keys(self):
        """
        ``Configuration._applications_from_configuration`` raises a
        ``ConfigurationError`` if the application_configuration has a port entry
        that has extra keys.
        """
        config = dict(
            version=1,
            applications={'mysql-hybridcluster': dict(
                image='busybox',
                ports=[{'internal': 90, 'external': 40, 'foo': 5, 'bar': 'six'}],
                )})
        parser = Configuration()
        exception = self.assertRaises(ConfigurationError,
                                      parser._applications_from_configuration,
                                      config)
        self.assertEqual(
            "Application 'mysql-hybridcluster' has a config error. "
            "Invalid ports specification. Unrecognised keys: bar, foo.",
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
        parser = Configuration()
        exception = self.assertRaises(ConfigurationError,
                                      parser._deployment_from_configuration,
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
        parser = Configuration()
        exception = self.assertRaises(ConfigurationError,
                                      parser._deployment_from_configuration,
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
        parser = Configuration()
        exception = self.assertRaises(ConfigurationError,
                                      parser._deployment_from_configuration,
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
        config = Configuration()
        exception = self.assertRaises(
            ConfigurationError,
            config._deployment_from_configuration,
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
        config = Configuration()
        exception = self.assertRaises(
            ConfigurationError,
            config._deployment_from_configuration,
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
        config = Configuration()
        result = config._deployment_from_configuration(
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
        config = Configuration()
        application_configuration = {'applications': {}, 'version': 1}
        deployment_configuration = {'nodes': {}, 'version': 1}
        result = config.model_from_configuration(
            application_configuration, deployment_configuration)
        expected_result = Deployment(nodes=frozenset())
        self.assertEqual(expected_result, result)

    def test_model_from_configuration(self):
        """
        ``Configuration.model_from_configuration`` returns a
        ``Deployment`` object with ``Nodes`` for each supplied node key.
        """
        config = Configuration()
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
        result = config.model_from_configuration(
            application_configuration, deployment_configuration)
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
                        ),
                    ])
                )
            ])
        )
        self.assertEqual(expected_result, result)
