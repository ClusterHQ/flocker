# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Functional tests for the volume manager service."""

from __future__ import absolute_import

from unittest import skipIf
import subprocess
import os
import json

from twisted.trial.unittest import TestCase
from twisted.python.filepath import FilePath

from ...testtools import random_name
from ..service import Volume, VolumeService
from ..filesystems.memory import FilesystemStoragePool


_if_root = skipIf(os.getuid() != 0, "Must run as root.")
# This is terible (https://github.com/clusterhq/flocker/issues/85):
_if_docker = skipIf(subprocess.Popen([b"docker", b"version"]).wait(),
                    "Docker must be installed and running.")


class VolumeTests(TestCase):
    """Tests for ``Volume``."""

    @_if_root
    @_if_docker
    def setUp(self):
        pass

    def add_container_cleanup(self, name):
        """Delete container with the given name when the test is over.

        :param bytes name: The name of the container to delete.
        """
        self.addCleanup(subprocess.check_call, [b"docker", b"rm", name])

    def test_expose_creates_container(self):
        """``Volume.expose_to_docker`` creates a Docker container."""
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        volume = Volume(uuid=u"myuuid", name=random_name(), _pool=pool)
        d = volume.expose_to_docker(FilePath(b"/my/path"))

        def exposed(_):
            self.add_container_cleanup(volume._container_name)
            data = subprocess.check_output(
                [b"docker", b"inspect", volume._container_name])
            self.assertTrue(json.loads(data))
        d.addCallback(exposed)
        return d

    def read_file_from_container(self, volume, path):
        """Return contents of file in the volume.

        :param Volume volume: The volume whose container we are checking.
        :param bytes path: Path within the container.
        :return: ``bytes`` of file at given path.
        """
        return subprocess.check_output(
            [b"docker", b"run", b"--rm",
             b"--volumes-from", volume._container_name,
             b"busybox", b"cat", path])

    def test_expose_mounted_volume(self):
        """``Volume.expose_to_docker`` mounts the volume's filesystem within
        this container at the given mount path."""
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool)
        service.startService()
        # We use VolumeService.create() so that the underlying filesystem
        # is created:
        d = service.create(random_name())

        def got_volume(volume):
            a_file = volume.get_filesystem().get_path().child(b"somefile.txt")
            a_file.setContent(b"I EXIST!")
            result = volume.expose_to_docker(FilePath(b"/my/path"))
            result.addCallback(lambda _: volume)
            return result
        d.addCallback(got_volume)

        def exposed(volume):
            self.add_container_cleanup(volume._container_name)
            data = self.read_file_from_container(
                volume, b"/my/path/somefile.txt")
            self.assertEqual(data, b"I EXIST!")
        d.addCallback(exposed)
        return d

    def test_expose_twice(self):
        """If ``Volume.expose_to_docker`` is called twice, the second given
        mount path overrides the first."""
        pool = FilesystemStoragePool(FilePath(self.mktemp()))
        service = VolumeService(FilePath(self.mktemp()), pool)
        service.startService()
        d = service.create(random_name())

        def got_volume(volume):
            a_file = volume.get_filesystem().get_path().child(b"somefile.txt")
            a_file.setContent(b"I EXIST!")
            result = volume.expose_to_docker(FilePath(b"/my/path"))
            result.addCallback(lambda _: volume.expose_to_docker(
                FilePath(b"/another/")))
            result.addCallback(lambda _: volume)
            return result
        d.addCallback(got_volume)

        def exposed(volume):
            self.add_container_cleanup(volume._container_name)
            data = self.read_file_from_container(
                volume, b"/another/somefile.txt")
            self.assertEqual(data, b"I EXIST!")
        d.addCallback(exposed)
        return d
