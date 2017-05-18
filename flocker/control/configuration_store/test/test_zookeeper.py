# Copyright (C) 2017 Nokia Corporation and/or its subsidiary(-ies). See LICENSE file for details.

"""
Tests for ``flocker.control.configuration_store.zookeeper``.
"""
import subprocess
from time import sleep

from ....testtools import AsyncTestCase
from ..testtools import IConfigurationStoreTestsMixin
from ..zookeeper import ZooKeeperConfigurationStore


class ZooKeeperConfigurationStoreInterfaceTests(IConfigurationStoreTestsMixin,
                                                AsyncTestCase):
    """
    Tests for ``ZooKeeperConfigurationStore``.
    """
    def _wait_for_zk(self, maxtries=15):
        cmd = ['docker', 'logs', self.docker_id]
        for _ in range(maxtries):
            subpr = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, _stderr = subpr.communicate()
            if 'binding to port' in stdout:
                return
            sleep(1)
        raise RuntimeError, 'Timed out waiting for Zookeeper container'

    def setUp(self):
        super(ZooKeeperConfigurationStoreInterfaceTests, self).setUp()
        self.docker_id = subprocess.check_output(
            ['docker', 'run', '-d', '--network=host', 'zookeeper:3.4']).strip()
        self._wait_for_zk()
        self.store = ZooKeeperConfigurationStore(
            zookeeper_hosts='localhost:2181'
        )

    def tearDown(self):
        super(ZooKeeperConfigurationStoreInterfaceTests, self).tearDown()
        subprocess.check_output(['docker', 'rm', '-f', self.docker_id])
