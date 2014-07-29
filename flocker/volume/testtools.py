# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Testing utilities provided by ``flocker.volume``.
"""

from twisted.python.filepath import FilePath
from twisted.internet.task import Clock

from .service import VolumeService
from .filesystems.memory import FilesystemStoragePool


def create_volume_service(test):
    """
    Create a new ``VolumeService`` suitable for use in unit tests.

    :param TestCase test: A unit test which will shut down the service
        when done.

    :return: The ``VolumeService`` created.
    """
    service = VolumeService(FilePath(test.mktemp()),
                            FilesystemStoragePool(FilePath(test.mktemp())),
                            reactor=Clock())
    service.startService()
    test.addCleanup(service.stopService)
    return service
