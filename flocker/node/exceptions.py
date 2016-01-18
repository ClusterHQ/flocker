# Copyright ClusterHQ Inc.  See LICENSE file for details.

from twisted.python.constants import NamedConstant


class StorageInitializationError(Exception):
    """
    Exception raised by a storage API factory in the event that
    the backend could not be successfully initialized.

    :param NamedConstant code: The ``StorageInitializationError`` constant
        indicating the type of failure.
    """
    CONFIGURATION_ERROR = NamedConstant()
    OPERATIVE_ERROR = NamedConstant()

    def __init__(self, code, *args):
        Exception.__init__(self, *args)
        self.code = code
