# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.node._config``.
"""

from __future__ import unicode_literals, absolute_import

from twisted.trial.unittest import SynchronousTestCase
from .._config import ConfigurationError, Configuration
from .._model import Application, DockerImage, Deployment, Node


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
        config = Configuration()
        self.assertRaises(ConfigurationError,
                          config._applications_from_configuration, {})

    def test_error_on_missing_application_attributes(self):
        """
        ``Configuration._applications_from_configuration`` raises a
        ``ConfigurationError`` if the application_configuration does not
        contain all the attributes of an ``Application`` record.
        """
        config = dict(applications={'mysql-hybridcluster': {}})
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
        config = dict(applications={
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
            applications={
                'mysql-hybridcluster': dict(image='flocker/mysql:v1.0.0'),
                'site-hybridcluster': dict(image='flocker/wordpress:v1.0.0')
            }
        )
        parser = Configuration()
        applications = parser._applications_from_configuration(config)
        expected_applications = {
            'mysql-hybridcluster': Application(
                name='mysql-hybridcluster',
                image=DockerImage(repository='flocker/mysql', tag='v1.0.0')),
            'site-hybridcluster': Application(
                name='site-hybridcluster',
                image=DockerImage(repository='flocker/wordpress',
                                  tag='v1.0.0'))
        }

        self.assertEqual(expected_applications, applications)


class DeploymentFromConfigurationTests(SynchronousTestCase):
    """
    Tests for ``Configuration._deployment_from_configuration``.
    """
    def test_error_on_missing_nodes_key(self):
        """
        ``_deployment_from_config`` raises a ``ConfigurationError`` if the
        deployment_configuration does not contain an ``u"nodes"`` key.
        """
        config = Configuration()
        self.assertRaises(
            ConfigurationError,
            config._deployment_from_configuration, {}, set())

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
            dict(nodes={'node1.example.com': None}),
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
            dict(nodes={'node1.example.com': ['site-hybridcluster']}),
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
            dict(nodes={'node1.example.com': ['mysql-hybridcluster']}),
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
        application_configuration = {'applications': {}}
        deployment_configuration = {'nodes': {}}
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
            'applications': {
                'mysql-hybridcluster': {'image': 'flocker/mysql:v1.2.3'},
                'site-hybridcluster': {'image': 'flocker/nginx:v1.2.3'}
            }
        }
        deployment_configuration = {
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
                            )
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
                            )
                        ),
                    ])
                )
            ])
        )
        self.assertEqual(expected_result, result)
