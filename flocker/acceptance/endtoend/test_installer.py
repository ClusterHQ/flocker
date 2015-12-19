# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for AWS CloudFormation installer.
"""

import os
import tarfile

from twisted.internet import reactor
from twisted.python.filepath import FilePath

from ...common.runner import run_ssh, download_file
from ...testtools import AsyncTestCase


class DockerComposeTests(AsyncTestCase):
    """
    Tests for AWS CloudFormation installer.
    """
    def test_docker_compose_up_mysql(self):
        """
        """
        client_ip = os.environ.get('CLIENT_IP')

        def docker_compose_up():
            docker_compose_output = []
            return run_ssh(
                reactor,
                'ubuntu',
                client_ip,
                ['docker-compose', '--help'],
                handle_stdout=docker_compose_output.append
            ).addCallback(
                lambda ignored: self.assertEqual("", docker_compose_output)
            )

        return docker_compose_up()
