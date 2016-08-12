# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Test helpers for ``flocker.node.agents.cinder``.
"""

from mimic.tap import makeService as mimic_make_service
from zope.interface.verify import verifyObject

from flocker.testtools import TestCase
from ..cinder import (
    ICinderVolumeManager,
    INovaVolumeManager,
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


def mimic_for_test(test_case):
    """
    Start a mimic server in the background on an ephemeral port and return the
    port number.

    This is used in synchronous test cases so I can't launch the mimic service
    in process.

    Parsing the logs for the chosen port number is ugly, but ``find_free_port``
    kept returning ports that were in use when mimic attempted to bind to them.
    """
    mimic_config = {
        "realtime": True,
        "listen": "0",
        "verbose": True,
    }
    mimic_service = mimic_make_service(mimic_config)
    mimic_service.startService()
    test_case.addCleanup(mimic_service.stopService)

    [site_service] = mimic_service.services
    waiting_for_port = site_service._waitingForPort

    def stop_the_port(listening_port):
        test_case.addCleanup(lambda: listening_port.stopListening())
        return listening_port

    listening = waiting_for_port.addCallback(stop_the_port)
    return listening
