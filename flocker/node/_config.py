# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
APIs for parsing and validating configuration.
"""

from ._model import Application, DockerImage


class Configuration(object):
    """
    
    """
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
                    ("Application '{application_name}' has a config error. "
                     "Invalid docker image name. {message}.").format(
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

    def model_from_configuration(self, application_configuration,
                                 deployment_configuration):
        applications = self._applications_from_configuration(
            application_configuration)
