# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_config -*-

"""
APIs for parsing and validating configuration.
"""

from __future__ import unicode_literals, absolute_import

import os
import types
import yaml

from twisted.python.filepath import FilePath

from ._model import (
    Application, AttachedVolume, Deployment, Link,
    DockerImage, Node, Port
)


class ConfigurationError(Exception):
    """
    Some part of the supplied configuration was wrong.

    The exception message will include some details about what.
    """


def _check_type(value, types, description, application_name):
    """
    Checks ``value`` has type in ``types``.

    :param value: Value whose type is to be checked
    :param tuple types: Tuple of types value can be.
    :param str description: Description of expected type.
    :param application_name unicode: Name of application whose config
        contains ``value``.

    :raises ConfigurationError: If ``value`` is not of type in ``types``.
    """
    if not isinstance(value, types):
        raise ConfigurationError(
            "Application '{application_name}' has a config "
            "error. {description}; got type '{type}'.".format(
                application_name=application_name,
                description=description,
                type=type(value).__name__,
            ))


class Configuration(object):
    """
    Validate and parse configurations.
    """
    def __init__(self, lenient=False):
        """
        :param bool lenient: If ``True`` don't complain about certain
            deficiencies in the output of ``flocker-reportstate``, In
            particular https://github.com/ClusterHQ/flocker/issues/289 means
            the mountpoint is unknown.
        """
        self._lenient = lenient

    def _parse_environment_config(self, application_name, config):
        """
        Validate and return an application config's environment variables.

        :param unicode application_name: The name of the application.

        :param dict config: The config of a single ``Application`` instance,
            as extracted from the ``applications`` ``dict`` in
            ``_applications_from_configuration``.

        :raises ConfigurationError: if the ``environment`` element of
            ``config`` is not a ``dict`` or ``dict``-like value.

        :returns: ``None`` if there is no ``environment`` element in the
            config, or the ``frozenset`` of environment variables if there is,
            in the form of a ``frozenset`` of ``tuple`` \s mapped to
            (key, value)

        """
        environment = config.pop('environment', None)
        if environment:
            _check_type(value=environment, types=(dict,),
                        description="'environment' must be a dictionary of "
                                    "key/value pairs",
                        application_name=application_name)
            for key, value in environment.iteritems():
                # We should normailzie strings to either bytes or unicode here
                # https://github.com/ClusterHQ/flocker/issues/636
                _check_type(value=key, types=types.StringTypes,
                            description="Environment variable name "
                                        "must be a string",
                            application_name=application_name)
                _check_type(value=value, types=types.StringTypes,
                            description="Environment variable '{key}' "
                                        "must be a string".format(key=key),
                            application_name=application_name)
            environment = frozenset(environment.items())
        return environment

    def _parse_link_configuration(self, application_name, config):
        """
        Validate and retrun an application config's links.

        :param unicode application_name: The name of the application

        :param dict config: The ``links`` configuration stanza of this
            application.

        :returns: A ``frozenset`` of ``Link``s specfied for this application.
        """
        links = []
        _check_type(value=config, types=(list,),
                    description="'links' must be a list of dictionaries",
                    application_name=application_name)
        try:
            for link in config:
                _check_type(value=link, types=(dict,),
                            description="Link must be a dictionary",
                            application_name=application_name)

                try:
                    local_port = link.pop('local_port')
                    _check_type(value=local_port, types=(int,),
                                description="Link's local port must be an int",
                                application_name=application_name)
                except KeyError:
                    raise ValueError("Missing local port.")

                try:
                    remote_port = link.pop('remote_port')
                    _check_type(value=remote_port, types=(int,),
                                description="Link's remote port "
                                            "must be an int",
                                application_name=application_name)
                except KeyError:
                    raise ValueError("Missing remote port.")

                try:
                    # We should normailzie strings to either bytes or unicode
                    # here. https://github.com/ClusterHQ/flocker/issues/636
                    alias = link.pop('alias')
                    _check_type(value=alias, types=types.StringTypes,
                                description="Link alias must be a string",
                                application_name=application_name)
                except KeyError:
                    raise ValueError("Missing alias.")

                if link:
                    raise ValueError(
                        "Unrecognised keys: {keys}.".format(
                            keys=', '.join(sorted(link))))
                links.append(Link(local_port=local_port,
                                  remote_port=remote_port,
                                  alias=alias))
        except ValueError as e:
            raise ConfigurationError(
                ("Application '{application_name}' has a config error. "
                 "Invalid links specification. {message}").format(
                     application_name=application_name, message=e.message))

        return frozenset(links)

    def _applications_from_configuration(self, application_configuration):
        """
        Validate and parse a given application configuration.

        :param dict application_configuration: The intermediate configuration
            representation to load into ``Application`` instances.  See
            :ref:`Configuration` for details.

        :raises ConfigurationError: if there are validation errors.

        :returns: A ``dict`` mapping application names to ``Application``
            instances.
        """
        if u'applications' not in application_configuration:
            raise ConfigurationError("Application configuration has an error. "
                                     "Missing 'applications' key.")

        if u'version' not in application_configuration:
            raise ConfigurationError("Application configuration has an error. "
                                     "Missing 'version' key.")

        if application_configuration[u'version'] != 1:
            raise ConfigurationError("Application configuration has an error. "
                                     "Incorrect version specified.")

        applications = {}
        for application_name, config in (
                application_configuration['applications'].items()):
            try:
                image_name = config.pop('image')
            except KeyError as e:
                raise ConfigurationError(
                    ("Application '{application_name}' has a config error. "
                     "Missing value for '{message}'.").format(
                        application_name=application_name, message=e.message)
                )

            try:
                image = DockerImage.from_string(image_name)
            except ValueError as e:
                raise ConfigurationError(
                    ("Application '{application_name}' has a config error. "
                     "Invalid Docker image name. {message}").format(
                        application_name=application_name, message=e.message)
                )

            ports = []
            try:
                for port in config.pop('ports', []):
                    try:
                        internal_port = port.pop('internal')
                    except KeyError:
                        raise ValueError("Missing internal port.")
                    try:
                        external_port = port.pop('external')
                    except KeyError:
                        raise ValueError("Missing external port.")

                    if port:
                        raise ValueError(
                            "Unrecognised keys: {keys}.".format(
                                keys=', '.join(sorted(port.keys()))))
                    ports.append(Port(internal_port=internal_port,
                                      external_port=external_port))
            except ValueError as e:
                raise ConfigurationError(
                    ("Application '{application_name}' has a config error. "
                     "Invalid ports specification. {message}").format(
                        application_name=application_name, message=e.message)
                )

            links = self._parse_link_configuration(
                application_name, config.pop('links', []))

            volume = None
            if "volume" in config:
                try:
                    configured_volume = config.pop('volume')
                    try:
                        mountpoint = configured_volume['mountpoint']
                    except TypeError:
                        raise ValueError(
                            "Unexpected value: " + str(configured_volume)
                        )
                    except KeyError:
                        raise ValueError("Missing mountpoint.")

                    if not (self._lenient and mountpoint is None):
                        if not isinstance(mountpoint, str):
                            raise ValueError(
                                "Mountpoint {path} contains non-ASCII "
                                "(unsupported).".format(
                                    path=mountpoint
                                )
                            )
                        if not os.path.isabs(mountpoint):
                            raise ValueError(
                                "Mountpoint {path} is not an absolute path."
                                .format(
                                    path=mountpoint
                                )
                            )
                        configured_volume.pop('mountpoint')
                        if configured_volume:
                            raise ValueError(
                                "Unrecognised keys: {keys}.".format(
                                    keys=', '.join(sorted(
                                        configured_volume.keys()))
                                ))
                        mountpoint = FilePath(mountpoint)

                    volume = AttachedVolume(
                        name=application_name,
                        mountpoint=mountpoint
                        )
                except ValueError as e:
                    raise ConfigurationError(
                        ("Application '{application_name}' has a config "
                         "error. Invalid volume specification. {message}")
                        .format(
                            application_name=application_name,
                            message=e.message
                        )
                    )

            environment = self._parse_environment_config(
                application_name, config)

            applications[application_name] = Application(
                name=application_name,
                image=image,
                volume=volume,
                ports=frozenset(ports),
                links=links,
                environment=environment)

            if config:
                raise ConfigurationError(
                    ("Application '{application_name}' has a config error. "
                     "Unrecognised keys: {keys}.").format(
                        application_name=application_name,
                        keys=', '.join(sorted(config.keys())))
                )
        return applications

    def _deployment_from_configuration(self, deployment_configuration,
                                       all_applications):
        """
        Validate and parse a given deployment configuration.

        :param dict deployment_configuration: The intermediate configuration
            representation to load into ``Node`` instances.  See
            :ref:`Configuration` for details.

        :param set all_applications: All applications which should be running
            on all nodes.

        :raises ConfigurationError: if there are validation errors.

        :returns: A ``set`` of ``Node`` instances.
        """
        if 'nodes' not in deployment_configuration:
            raise ConfigurationError("Deployment configuration has an error. "
                                     "Missing 'nodes' key.")

        if u'version' not in deployment_configuration:
            raise ConfigurationError("Deployment configuration has an error. "
                                     "Missing 'version' key.")

        if deployment_configuration[u'version'] != 1:
            raise ConfigurationError("Deployment configuration has an error. "
                                     "Incorrect version specified.")

        nodes = []
        for hostname, application_names in (
                deployment_configuration['nodes'].items()):
            if not isinstance(application_names, list):
                raise ConfigurationError(
                    "Node {node_name} has a config error. "
                    "Wrong value type: {value_type}. "
                    "Should be list.".format(
                        node_name=hostname,
                        value_type=application_names.__class__.__name__)
                )
            node_applications = []
            for name in application_names:
                application = all_applications.get(name)
                if application is None:
                    raise ConfigurationError(
                        "Node {hostname} has a config error. "
                        "Unrecognised application name: "
                        "{application_name}.".format(
                            hostname=hostname, application_name=name)
                    )
                node_applications.append(application)
            node = Node(hostname=hostname,
                        applications=frozenset(node_applications))
            nodes.append(node)
        return set(nodes)

    def model_from_configuration(self, application_configuration,
                                 deployment_configuration):
        """
        Validate and coerce the supplied application configuration and
        deployment configuration dictionaries into a ``Deployment`` instance.

        :param dict application_configuration: Map of applications to Docker
            images.

        :param dict deployment_configuration: Map of node names to application
            names.

        :raises ConfigurationError: if there are validation errors.

        :returns: A ``Deployment`` object.
        """
        applications = self._applications_from_configuration(
            application_configuration)
        nodes = self._deployment_from_configuration(
            deployment_configuration, applications)
        return Deployment(nodes=frozenset(nodes))


model_from_configuration = Configuration().model_from_configuration


def current_from_configuration(current_configuration):
    """
    Validate and coerce the supplied current cluster configuration into a
    ``Deployment`` instance.

    The passed in configuration is the aggregated output of
    ``configuration_to_yaml`` as combined by ``flocker-deploy``.

    :param dict current_configuration: Map of node names to list of
        application maps.

    :raises ConfigurationError: if there are validation errors.

    :returns: A ``Deployment`` object.
    """
    configuration = Configuration(lenient=True)
    nodes = []
    for hostname, applications in current_configuration.items():
        node_applications = configuration._applications_from_configuration(
            applications)
        nodes.append(Node(hostname=hostname,
                          applications=frozenset(node_applications.values())))
    return Deployment(nodes=frozenset(nodes))


def configuration_to_yaml(applications):
    """
    Generate YAML representation of a node's applications.

    A bunch of information is missing, but this is sufficient for the
    initial requirement of determining what to do about volumes when
    applying configuration changes.
    https://github.com/ClusterHQ/flocker/issues/289

    :param applications: ``list`` of ``Application``\ s, typically the
        current configuration on a node as determined by
        ``Deployer.discover_node_configuration()``.

    :return: YAML serialized configuration in the application
        configuration format.
    """
    result = {}
    for application in applications:
        # XXX image unknown, see
        # https://github.com/ClusterHQ/flocker/issues/207
        result[application.name] = {"image": "unknown"}

        ports = []
        for port in application.ports:
            ports.append(
                {'internal': port.internal_port,
                 'external': port.external_port}
            )
        result[application.name]["ports"] = ports

        if application.links:
            links = []
            for link in application.links:
                links.append({
                    'local_port': link.local_port,
                    'remote_port': link.remote_port,
                    'alias': link.alias,
                    })
            result[application.name]["links"] = links

        if application.volume:
            # Until multiple volumes are supported, assume volume name
            # matches application name, see:
            # https://github.com/ClusterHQ/flocker/issues/49
            result[application.name]["volume"] = {
                "mountpoint": None,
            }
    return yaml.safe_dump({"version": 1, "applications": result})
