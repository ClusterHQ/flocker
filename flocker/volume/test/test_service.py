# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Tests for :module:`flocker.volume.service`."""

from __future__ import absolute_import

import json

from zope.interface.verify import verifyObject

from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase
from twisted.application.service import IService

from ..service import VolumeService


class VolumeServiceTests(TestCase):
    """
    Tests for :class:`VolumeService`.
    """
    def test_interface(self):
        """:class:`VolumeService` implements :class:`IService`."""
        self.assertTrue(verifyObject(IService, VolumeService(FilePath(""))))

    def test_no_config_UUID(self):
        """If no config file exists in the given path, a new UUID is chosen."""
        service = VolumeService(FilePath(self.mktemp()))
        service.startService()
        service2 = VolumeService(FilePath(self.mktemp()))
        service2.startService()
        self.assertNotEqual(service.uuid, service2.uuid)

    def test_no_config_written(self):
        """If no config file exists, a new one is written with the UUID."""
        path = FilePath(self.mktemp())
        service = VolumeService(path)
        service.startService()
        config = json.loads(path.getContent())
        self.assertEqual({u"uuid": service.uuid, u"version": 1}, config)

    def test_config(self):
        """If a config file exists, the UUID is loaded from it."""
        path = self.mktemp()
        service = VolumeService(FilePath(path))
        service.startService()
        service2 = VolumeService(FilePath(path))
        service2.startService()
        self.assertEqual(service.uuid, service2.uuid)
