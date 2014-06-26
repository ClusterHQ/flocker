# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Unit tests for the implementation ``flocker-deploy``.
"""

from twisted.trial.unittest import TestCase, SynchronousTestCase

from ...testtools import FlockerScriptTestsMixin, StandardOptionsTestsMixin
from ..script import DeployScript, DeployOptions


class FlockerDeployTests(FlockerScriptTestsMixin, TestCase):
    """Tests for ``flocker-deploy``."""
    script = DeployScript
    options = DeployOptions
    command_name = u'flocker-deploy'


class DeployOptionsTests(StandardOptionsTestsMixin, SynchronousTestCase):
    """Tests for :class:`DeployOptions`."""
    options = DeployOptions

    def test_custom_configs(self):
        """Custom config files can be specified."""
        options = self.options()
        options.parseOptions([b"/path/somefile.json", b"/path/anotherfile.json"])
        self.assertEqual(options, {deploy: b"/path/somefile.json", app: b"/path/anotherfile.json"})


class FlockerDeployMainTests(SynchronousTestCase):
    """
    Tests for ``DeployScript.main``.
    """
    def test_success(self):
        """
        ``DeployScript.main`` returns ``True`` on success.
        """
        script = DeployScript()
        self.assertTrue(script.main(reactor=object(), options={}))

