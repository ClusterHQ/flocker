# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Functional tests for the volume manager service."""

from __future__ import absolute_import

from random import random
from unittest import skipIf
import subprocess
import os
import json

from twisted.trial.unittest import TestCase
from twisted.python.filepath import FilePath

from ..service import Volume
from ..filesystems.memory import FilesystemStoragePool


def random_name():
    """Return a random volume name.

    :return unicode name: A random name.
    """
    return u"%d" % (int(random() * 1e12),)


_if_root = skipIf(os.getuid() != 0, "Must run as root.")


class VolumeTests(TestCase):
    """Tests for ``Volume``."""

    @_if_root
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
        name = random_name()
        volume = Volume(uuid=u"myuuid", name=name, _pool=pool)
        d = volume.expose_to_docker(FilePath(b"/my/path"))

        def exposed(_):
            self.add_container_cleanup(volume._container_name)
            data = subprocess.check_output(
                [b"docker", b"inspect", volume._container_name])
            self.assertTrue(json.loads(data))
        d.addCallback(exposed)
        return d

    def test_expose_mounted_volume(self):
        """``Volume.expose_to_docker`` mounts the volume's filesystem within
        this container at the given mount path."""

    def test_expose_twice(self):
        """If ``Volume.expose_to_docker`` is called twice, the second given
        mount path overrides the first."""
