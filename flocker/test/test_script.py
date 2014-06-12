# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for :module:`flocker.script`.
"""

from __future__ import absolute_import

import io, sys

from twisted.trial.unittest import SynchronousTestCase

from ..script import FlockerVolumeOptions
from .. import __version__


class StandardOptionsTestsMixin(object):
    """
    Tests for the standard options that should be available on every flocker
    command.
    """
    options = None

    def test_version(self):
        """
        Flocker commands have a I{--version} option which prints the current
        version string to stdout and causes the command to exit with status 0.
        """
        output = io.BytesIO()
        self.patch(sys, 'stdout', output)
        error = self.assertRaises(
            SystemExit,
            self.options().parseOptions,
            ['--version']
        )
        self.assertEqual(
            (__version__ + '\n', 0),
            (output.getvalue(), error.code)
        )



class FlockerVolumeOptionsTests(StandardOptionsTestsMixin, SynchronousTestCase):
    """
    Tests for L{FlockerVolumeOptions}.
    """
    options = FlockerVolumeOptions
