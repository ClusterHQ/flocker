# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.node._config``.
"""

from twisted.trial.unittest import SynchronousTestCase
from .._config import Configuration


class ModelFromConfigurationTests(SynchronousTestCase):
    """
    Other tests for ``model_from_configuration``.
    """
    def test_error_on_missing_application_key(self):
        """
        ``model_from_configuration`` raises an exception if the
        application_configuration does not contain an `application` key.
        """

    def test_error_on_missing_application_attributes(self):
        """
        ``model_from_configuration`` raises an exception if the
        application_configuration does not contain all the attributes of an
        `Application` record.
        """

    def test_error_on_extra_application_attributes(self):
        """
        ``model_from_configuration`` raises an exception if the
        application_configuration contains unrecognised Application attribute
        names.
        """
        
    def test_error_invalid_dockerimage_name(self):
        """
        ``model_from_configuration`` raises an exception if the
        application_configuration uses invalid docker image names.
        """

    def test_error_on_invalid_volume_path(self):
        """
        ``model_from_configuration`` raises an exception if the
        application_configuration uses invalid unix paths for volumes.
        """

    def test_dict_of_applications(self):
        """
        ``model_from_configuration`` returns a dict of ``Application``
        instances, one for each application key in the supplied configuration.
        """




        
