# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for :module:`flocker.script`.
"""

from __future__ import absolute_import

from twisted.trial.unittest import SynchronousTestCase
from twisted.application.service import IServiceMaker, IServiceCollection
from twisted.plugin import getPlugins
from zope.interface.verify import verifyObject

from click.testing import CliRunner

from ..script import flocker
from .. import __version__


class FlockerTests(SynchronousTestCase):
    """
    """
    def test_noArguments(self):
        """
        When run without any arguments flocker prints nothing and exits with
        status 0.
        """
        runner = CliRunner()
        result = runner.invoke(flocker, [])
        self.assertEqual(
            (0, u'\n'),
            (result.exit_code, result.output)
        )


    def test_help(self):
        """
        When run without a help argument, the flocker command prints online
        help and exits with status 0.
        """
        runner = CliRunner()
        result = runner.invoke(flocker, ['--help'])
        self.assertEqual(
            (0, u'Usage'),
            (result.exit_code, result.output[:len(u'Usage')])
        )


    def test_version(self):
        """
        When run with a version argument, the flocker command prints the flocker
        version and exits with status 0
        """
        runner = CliRunner()
        result = runner.invoke(flocker, ['--version'])
        self.assertEqual(
            (0, u'flocker, version {version}\n'.format(version=__version__)),
            (result.exit_code, result.output)
        )



