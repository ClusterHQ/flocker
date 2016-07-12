# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Test helpers for ``flocker.node.agents.cinder``.
"""
from itertools import repeat
import os
import re
from subprocess import Popen

from zope.interface.verify import verifyObject

from flocker.testtools import TestCase
from ....common import poll_until
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
    log = test_case.make_temporary_path()
    stdout = test_case.make_temporary_path()
    stderr = test_case.make_temporary_path()
    with stdout.open('w') as stdout, stderr.open('w') as stderr:
        p = Popen(['twistd', '--nodaemon', '--logfile', log.path,
                   'mimic', '--listen', '0', '--realtime'],
                  stdin=open(os.devnull), stdout=stdout, stderr=stderr,
                  close_fds=True)

    def cleanup():
        p.terminate()
        p.wait()
    test_case.addCleanup(cleanup)

    poll_until(
        predicate=log.exists,
        steps=repeat(1, 5)
    )

    def port_from_log():
        for line in log.open():
            match = re.search(r"Site starting on (\d+)$", line)
            if match:
                port = match.group(1)
                return int(port)

    return poll_until(
        predicate=port_from_log,
        steps=repeat(1, 5)
    )
