# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
Tests for ``flocker.control.configuration_store.filepath``.
"""
from ..directory import DirectoryConfigurationStore
from ..testtools import make_iconfigurationstore_tests


def directory_store_for_test(test):
    return DirectoryConfigurationStore(
        directory=test.make_temporary_directory()
    )


class DirectoryConfigurationStoreInterfaceTests(
        make_iconfigurationstore_tests(
            store_factory=directory_store_for_test
        )
):
    """
    Tests for ``DirectoryConfigurationStore``.
    """
