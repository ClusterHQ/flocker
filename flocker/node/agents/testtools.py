# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Test helpers for ``flocker.node.agents``.
"""

from zope.interface.verify import verifyObject

from flocker.testtools import TestCase
from .cinder import (
    ICinderVolumeManager, INovaVolumeManager,
)


class ICinderVolumeManagerTestsMixin(object):
    """
    Tests for ``ICinderVolumeManager`` implementations.
    """
    def test_interface(self):
        """
        ``client`` provides ``ICinderVolumeManager``.
        """
        self.assertTrue(verifyObject(ICinderVolumeManager, self.client))


def make_icindervolumemanager_tests(client_factory):
    """
    Build a ``TestCase`` for verifying that an implementation of
    ``ICinderVolumeManager`` adheres to that interface.
    """
    class Tests(ICinderVolumeManagerTestsMixin, TestCase):
        def setUp(self):
            super(Tests, self).setUp()
            self.client = client_factory(test_case=self)

    return Tests


class INovaVolumeManagerTestsMixin(object):
    """
    Tests for ``INovaVolumeManager`` implementations.
    """
    def test_interface(self):
        """
        ``client`` provides ``INovaVolumeManager``.
        """
        self.assertTrue(verifyObject(INovaVolumeManager, self.client))


def make_inovavolumemanager_tests(client_factory):
    """
    Build a ``TestCase`` for verifying that an implementation of
    ``INovaVolumeManager`` adheres to that interface.
    """
    class Tests(INovaVolumeManagerTestsMixin, TestCase):
        def setUp(self):
            super(Tests, self).setUp()
            self.client = client_factory(test_case=self)

    return Tests
