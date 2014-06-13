# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Tests for :module:`flocker.volume.service`."""

from __future__ import absolute_import

import json
import os
from unittest import skipIf

from zope.interface.verify import verifyObject

from twisted.python.filepath import FilePath, Permissions
from twisted.trial.unittest import TestCase
from twisted.application.service import IService

from ..service import VolumeService, CreateConfigurationError, Volume
from ..filesystems.memory import FilesystemStoragePool


class VolumeServiceStartupTests(TestCase):
    """
    Tests for :class:`VolumeService` startup.
    """
    def test_interface(self):
        """:class:`VolumeService` implements :class:`IService`."""
        self.assertTrue(verifyObject(IService,
                                     VolumeService(FilePath(""), None)))

    def test_no_config_UUID(self):
        """If no config file exists in the given path, a new UUID is chosen."""
        service = VolumeService(FilePath(self.mktemp()), None)
        service.startService()
        service2 = VolumeService(FilePath(self.mktemp()), None)
        service2.startService()
        self.assertNotEqual(service.uuid, service2.uuid)

    def test_no_config_written(self):
        """If no config file exists, a new one is written with the UUID."""
        path = FilePath(self.mktemp())
        service = VolumeService(path, None)
        service.startService()
        config = json.loads(path.getContent())
        self.assertEqual({u"uuid": service.uuid, u"version": 1}, config)

    def test_no_config_directory(self):
        """The config file's parent directory is created if it doesn't exist."""
        path = FilePath(self.mktemp()).child(b"config.json")
        service = VolumeService(path, None)
        service.startService()
        self.assertTrue(path.exists())

    @skipIf(os.getuid() == 0, "root doesn't get permission errors.")
    def test_config_makedirs_failed(self):
        """If creating the config directory fails then CreateConfigurationError
        is raised."""
        path = FilePath(self.mktemp())
        path.makedirs()
        path.chmod(0)
        self.addCleanup(path.chmod, 0o777)
        path = path.child(b"dir").child(b"config.json")
        service = VolumeService(path, None)
        self.assertRaises(CreateConfigurationError, service.startService)

    @skipIf(os.getuid() == 0, "root doesn't get permission errors.")
    def test_config_write_failed(self):
        """If writing the config fails then CreateConfigurationError
        is raised."""
        path = FilePath(self.mktemp())
        path.makedirs()
        path.chmod(0)
        self.addCleanup(path.chmod, 0o777)
        path = path.child(b"config.json")
        service = VolumeService(path, None)
        self.assertRaises(CreateConfigurationError, service.startService)

    def test_config(self):
        """If a config file exists, the UUID is loaded from it."""
        path = self.mktemp()
        service = VolumeService(FilePath(path), None)
        service.startService()
        service2 = VolumeService(FilePath(path), None)
        service2.startService()
        self.assertEqual(service.uuid, service2.uuid)


class VolumeServiceAPITests(TestCase):
    """Tests for the ``VolumeService`` API."""

    def test_create_result(self):
        """``create()`` returns a ``Deferred`` that fires with a ``Volume``."""
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool)
        service.startService()
        d = service.create(u"myvolume")
        self.assertEqual(
            self.successResultOf(d),
            Volume(uuid=service.uuid, name=u"myvolume", _pool=pool))

    def test_create_filesystem(self):
        """``create()`` creates the volume's filesystem."""
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool)
        service.startService()
        volume = self.successResultOf(service.create(u"myvolume"))
        self.assertTrue(pool.get(volume).get_mountpoint().isdir())

    def test_create_mode(self):
        """The created filesystem is readable/writable/executable by anyone.

        A better alternative will be implemented in
        https://github.com/hybridlogic/flocker/issues/34
        """
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool)
        service.startService()
        volume = self.successResultOf(service.create(u"myvolume"))
        self.assertEqual(pool.get(volume).get_mountpoint().getPermissions(),
                         Permissions(0777))


class VolumeTests(TestCase):
    """Tests for ``Volume``."""

    def test_equality(self):
        """Volumes are equal if they have the same name, uuid and pool."""
        pool = object()
        v1 = Volume(uuid=u"123", name=u"456", _pool=pool)
        v2 = Volume(uuid=u"123", name=u"456", _pool=pool)
        self.assertTrue(v1 == v2)
        self.assertFalse(v1 != v2)

    def test_inequality_uuid(self):
        """Volumes are unequal if they have different uuids."""
        pool = object()
        v1 = Volume(uuid=u"123", name=u"456", _pool=pool)
        v2 = Volume(uuid=u"123zz", name=u"456", _pool=pool)
        self.assertTrue(v1 != v2)
        self.assertFalse(v1 == v2)

    def test_inequality_name(self):
        """Volumes are unequal if they have different names."""
        pool = object()
        v1 = Volume(uuid=u"123", name=u"456", _pool=pool)
        v2 = Volume(uuid=u"123", name=u"456zz", _pool=pool)
        self.assertTrue(v1 != v2)
        self.assertFalse(v1 == v2)

    def test_inequality_pool(self):
        """Volumes are unequal if they have different pools."""
        v1 = Volume(uuid=u"123", name=u"456", _pool=object())
        v2 = Volume(uuid=u"123", name=u"456", _pool=object())
        self.assertTrue(v1 != v2)
        self.assertFalse(v1 == v2)

    def test_get_filesystem(self):
        """``Volume.get_filesystem`` returns the filesystem for the volume."""
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        volume = Volume(uuid=u"123", name=u"456", _pool=pool)
        self.assertEqual(volume.get_filesystem(), pool.get(volume))
