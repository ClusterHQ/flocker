# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
APIs for parsing and validating configuration.
"""

from ._model import Application, DockerImage

class Configuration(object):

    def _applications_from_configuration(self, application_configuration):
        if 'applications' not in application_configuration:
            raise KeyError('Missing applications key')

        applications = {}
        for application_name, config in application_configuration['applications'].items():
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
                    ("Application '{application_name}' has a config error. Invalid docker image name. "
                     "{message}").format(
                         application_name=application_name, message=e.message)
                )

            applications[application_name] = Application(name=application_name, image=image)

            if config:
                raise KeyError(
                    ("Application '{application_name}' has a config error. "
                     "Unrecognised keys: {keys}").format(
                         application_name=application_name, keys=', '.join(config.keys()))
                )
        return applications

    def _deployment_from_configuration(self, deployment_configuration):
        if 'nodes' not in deployment_configuration:
            raise KeyError('Missing nodes key')

        for hostname, applications in deployment_configuration['nodes'].items():
            if not isinstance(applications, list):
                raise ValueError(
                    "Node {node_name} has a config error. "
                    "Wrong value type: {value_type}. "
                    "Should be list.".format(node_name=hostname,
                                             value_type=applications.__class__.__name__)
                )

    def model_from_configuration(self, application_configuration, deployment_configuration):
        applications = self._applications_from_configuration(application_configuration)
