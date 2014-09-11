# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Functional tests for :module:`flocker.node.docker`.
"""

from unittest import skipIf
from subprocess import Popen

from ..test.test_gear import make_igearclient_tests
from ..docker import DockerClient


# This is terible (https://github.com/ClusterHQ/flocker/issues/85):
_if_docker = skipIf(Popen([b"docker", b"version"]).wait(),
                    "Docker must be installed and running.")


class IGearClientTests(make_igearclient_tests(
        lambda test_case: DockerClient())):
    """
    ``IGearClient`` tests for ``DockerClient``.
    """

    @_if_docker
    def setUp(self):
        pass
