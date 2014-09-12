# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for :module:`flocker.node.docker`.
"""

from unittest import skipIf
from subprocess import Popen

from docker.errors import APIError
from docker import Client

from twisted.trial.unittest import TestCase

from ...testtools import random_name
from ..test.test_gear import make_igearclient_tests
from ..functional.test_gear import GearClientTestsMixin
from ..docker import DockerClient


# This is terible (https://github.com/ClusterHQ/flocker/issues/85):
_if_docker = skipIf(Popen([b"docker", b"version"]).wait(),
                    "Docker must be installed and running.")


class IGearClientTests(make_igearclient_tests(
        lambda test_case: DockerClient(namespace=random_name()))):
    """
    ``IGearClient`` tests for ``DockerClient``.
    """
    @_if_docker
    def setUp(self):
        pass


class DockerClientTests(GearClientTestsMixin, TestCase):
    """
    Functional tests for ``DockerClient``.
    """
    @_if_docker
    def setUp(self):
        pass

    clientException = APIError

    def make_client(self):
        # The gear tests which we're (temporarily) reusing assume
        # container name matches unit name, so we disable namespacing for
        # these tests.
        return DockerClient(namespace=u"")

    def test_pull_image_if_necessary(self):
        """
        The Docker image is pulled if it is unavailable locally.
        """
        image = u"busybox"
        # Make sure image is gone:
        docker = Client()
        try:
            docker.remove_image(image)
        except APIError as e:
            if e.response.status_code != 404:
                raise

        name = random_name()
        client = self.make_client()
        self.addCleanup(client.remove, name)
        d = client.add(name, image)
        d.addCallback(lambda _: self.assertTrue(docker.inspect_image(image)))
        return d

    def test_namespacing(self):
        """
        Containers are created with the ``DockerClient`` namespace prefixed to
        their container name.
        """
        docker = Client()
        name = random_name()
        client = DockerClient(namespace=u"testing-")
        self.addCleanup(client.remove, name)
        d = client.add(name, u"busybox")
        d.addCallback(lambda _: self.assertTrue(
            docker.inspect_container(u"testing-" + name)))
        return d

    def test_default_namespace(self):
        """
        The default namespace is `u"flocker--"`.
        """
        docker = Client()
        name = random_name()
        client = DockerClient()
        self.addCleanup(client.remove, name)
        d = client.add(name, u"busybox")
        d.addCallback(lambda _: self.assertTrue(
            docker.inspect_container(u"flocker--" + name)))
        return d
