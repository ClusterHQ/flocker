# Copyright ClusterHQ Inc.  See LICENSE file for details.

import os

from twisted.python.filepath import FilePath
from ...testtools import (
    make_flocker_script_test, make_standard_options_test, TestCase,
)
from .._script import CAScript, CAOptions


class FlockerCATests(
        make_flocker_script_test(CAScript, CAOptions, u'flocker-ca')
):
    """
    Tests for ``flocker-ca`` CLI.
    """


class CAOptionsTests(make_standard_options_test(CAOptions)):
    """
    Tests for :class:`CAOptions`.
    """


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

        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        os.chdir(path.path)

        options = CAOptions()
        options.parseOptions(["initialize", "mycluster"])

        script = CAScript()
        dummy_reactor = object()

        self.assertEqual(
            None,
            self.successResultOf(script.main(dummy_reactor, options))
        )
