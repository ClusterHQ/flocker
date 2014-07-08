# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
APIs for parsing and validating configuration.
"""

from ._model import Application, DockerImage, Node, Deployment


class Configuration(object):
    """
    Validate and parse configurations.
    """
    def _applications_from_configuration(self, application_configuration):
        """
        Validate and parse a given application configuration.

        :param dict application_configuration: Map of applications to Docker
            images.
        :raises KeyError: if there are validation errors.
        """
        if 'applications' not in application_configuration:
            raise KeyError('Missing applications key')

        applications = {}
        for application_name, config in (
            application_configuration['applications'].items()):
            try:
                image_name = config.pop('image')
            except KeyError as e:
                raise KeyError(
                    ("Application '{application_name}' has a config error. "
                     "Missing value for '{message}'.").format(
                         application_name=application_name, message=e.message)
                )

            try:
                image = DockerImage.from_string(image_name)
            except ValueError as e:
                raise KeyError(
                    ("Application '{application_name}' has a config error. "
                     "Invalid Docker image name. {message}").format(
                         application_name=application_name, message=e.message)
                )

            applications[application_name] = Application(name=application_name,
                                                         image=image)

            if config:
                raise KeyError(
                    ("Application '{application_name}' has a config error. "
                     "Unrecognised keys: {keys}.").format(
                         application_name=application_name,
                         keys=', '.join(config.keys()))
                )
        return applications

    def _deployment_from_configuration(self, deployment_configuration, all_applications):
        if 'nodes' not in deployment_configuration:
            raise KeyError('Missing nodes key')

        nodes = []

        for hostname, application_names in deployment_configuration['nodes'].items():
            if not isinstance(application_names, list):
                raise ValueError(
                    "Node {node_name} has a config error. "
                    "Wrong value type: {value_type}. "
                    "Should be list.".format(node_name=hostname,
                                             value_type=application_names.__class__.__name__)
                )
            node_applications = []
            for name in application_names:
                application = all_applications.get(name)
                if application is None:
                    raise ValueError(
                        "Node {hostname} has a config error. "
                        "Unrecognised application name: {application_name}.".format(
                            hostname=hostname, application_name=name)
                    )
                node_applications.append(application)
            node = Node(hostname=hostname, applications=frozenset(node_applications))
            nodes.append(node)
        return set(nodes)

    def model_from_configuration(self, application_configuration, deployment_configuration):
        applications = self._applications_from_configuration(application_configuration)
        nodes = self._deployment_from_configuration(deployment_configuration, applications)
        return Deployment(nodes=frozenset(nodes))


model_from_configuration = Configuration().model_from_configuration
