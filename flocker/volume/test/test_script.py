# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for :module:`flocker.volume.script`.
"""

from twisted.python.filepath import FilePath
from twisted.application.service import Service
from twisted.python.usage import Options

from ...testtools import make_standard_options_test, TestCase
from ..testtools import make_volume_options_tests

from ..script import (
    VolumeOptions, VolumeManagerScript, flocker_volume_options
)


class VolumeManagerScriptMainTests(TestCase):
    """
    Tests for ``VolumeManagerScript.main``.
    """
    def test_deferred_result(self):
        """
        ``VolumeScript.main`` returns a ``Deferred`` on success.
        """
        script = VolumeManagerScript()
        options = VolumeOptions()
        options["config"] = FilePath(self.mktemp())
        dummy_reactor = object()
        result = script.main(dummy_reactor, options, Service())
        self.assertIs(None, self.successResultOf(result))


class VolumeOptionsTests(make_standard_options_test(VolumeOptions)):
    """
    Tests for :class:`VolumeOptions`.
    """


@flocker_volume_options
class DummyVolumeOptions(Options):
    """
    An ``Options`` class that uses ``flocker_volume_options`` for the purposes
    of testing.
    """


class MakeVolumeOptionsTests(make_volume_options_tests(DummyVolumeOptions)):
    """
    Tests for ``make_volume_options``.
    """


class StandardVolumeOptionsTests(make_volume_options_tests(VolumeOptions)):
    """
    Tests for ``VolumeService`` specific arguments of ``VolumeOptions``.
    """
