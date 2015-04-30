# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

import os

from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase, SynchronousTestCase
from ...testtools import FlockerScriptTestsMixin
from .._script import CAScript, CAOptions


class FlockerCATests(FlockerScriptTestsMixin, TestCase):
    """
    Tests for ``flocker-ca`` CLI.
    """
    script = CAScript
    options = CAOptions
    command_name = u'flocker-ca'


class CAOptionsTests(SynchronousTestCase):
    """
    Tests for :class:`CAOptions`.
    """
    options = CAOptions


class FlockerCAMainTests(TestCase):
    """
    Tests for ``CAScript.main``.
    """
    def test_deferred_result(self):
        """
        ``CAScript.main`` returns a ``Deferred`` on success.
        """
        # Ensure we don't conflict on buildbot with certificate
        # files already created in previous tests.
        path = FilePath(self.mktemp())
        path.makedirs()
        os.chdir(path.path)

        options = CAOptions()
        options.parseOptions(["initialize", "mycluster"])

        script = CAScript()
        dummy_reactor = object()

        self.assertEqual(
            None,
            self.successResultOf(script.main(dummy_reactor, options))
        )
