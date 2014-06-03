"""
Tests for :module:`flocker.volume.service`.
"""

from zope.interface.verify import verifyObject

from twisted.trial.unittest import TestCase
from twisted.application.service import IService

from ..service import VolumeService


class VolumeServiceTests(TestCase):
    """
    Tests for :class:`VolumeService`.
    """
    def test_interface(self):
        """:class:`VolumeService` implements :class:`IService`."""
        self.assertTrue(verifyObject(IService, VolumeService()))
