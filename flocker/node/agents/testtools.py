# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Test helpers for ``flocker.node.agents``.
"""
import os
import yaml

from zope.interface.verify import verifyObject
from zope.interface import implementer

from twisted.trial.unittest import SynchronousTestCase, SkipTest
from twisted.python.components import proxyForInterface

from .cinder import (
    ICinderVolumeManager, INovaVolumeManager, wait_for_volume,
)


DEFAULT_OPENSTACK_PROVIDER = 'rackspace'


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
    class Tests(ICinderVolumeManagerTestsMixin, SynchronousTestCase):
        def setUp(self):
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
    class Tests(INovaVolumeManagerTestsMixin, SynchronousTestCase):
        def setUp(self):
            self.client = client_factory(test_case=self)

    return Tests
