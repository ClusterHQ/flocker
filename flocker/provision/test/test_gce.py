# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for GCE provisioner.
"""

from zope.interface.verify import verifyClass

from ...testtools import TestCase
from .._common import IProvisioner
from .._gce import GCEProvisioner


class GCEProvisionerTests(TestCase):
    """
    Tests for :class:`GCEProvisioner`.
    """

    def test_implements_iprovisioner(self):
        """
        Verify that :class:`GCEProvisioner` implements the
        :class:`IProvisioner` interface.
        """
        verifyClass(IProvisioner, GCEProvisioner)
