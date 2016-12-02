# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
Tests for ``flocker.control.configuration_store.filepath``.
"""
from ....testtools import AsyncTestCase

from ..directory import DirectoryConfigurationStore
from ..testtools import IConfigurationStoreTestsMixin


class DirectoryConfigurationStoreInterfaceTests(IConfigurationStoreTestsMixin,
                                                AsyncTestCase):
    """
    Tests for ``DirectoryConfigurationStore``.
    """
    def setUp(self):
        super(DirectoryConfigurationStoreInterfaceTests, self).setUp()
        self.store = DirectoryConfigurationStore(
            directory=self.make_temporary_directory()
        )
