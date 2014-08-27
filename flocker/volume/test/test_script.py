# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for :module:`flocker.volume.script`.
"""

from twisted.trial.unittest import SynchronousTestCase
from twisted.python.filepath import FilePath
from twisted.application.service import Service
from twisted.python.usage import Options

from ...testtools import (
    StandardOptionsTestsMixin
)
from ..testtools import (
    make_volume_options_tests
)
from ..script import (
    VolumeOptions, VolumeManagerScript, flocker_volume_options
)


class VolumeManagerScriptMainTests(SynchronousTestCase):
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


class VolumeOptionsTests(StandardOptionsTestsMixin, SynchronousTestCase):
    """
    Tests for :class:`VolumeOptions`.
    """
    options = VolumeOptions


@flocker_volume_options
class DummyVolumeOptions(Options):
    """
    An ``Options`` class that uses ``flocker_volume_options`` for the purposes
    of testing.
    """


MakeVolumeOptionsTests = make_volume_options_tests(DummyVolumeOptions)

StandardVolumeOptionsTests = make_volume_options_tests(VolumeOptions)
