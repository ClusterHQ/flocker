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

from ..script import flocker, volume, FilePath
from .. import __version__


def assertHelp(testCase, command, arguments):
    """

    """
    runner = CliRunner()
    result = runner.invoke(command, arguments)

    testCase.assertEqual(
        (0, u'Usage'),
        (result.exit_code, result.output[:len(u'Usage')])
    )



class CommonArgumentsTestsMixin(object):
    def test_help(self):
        """
        When run with a help argument, the flocker prints help text and exits
        with status 0.
        """
        assertHelp(self, flocker, ['--help'])


    def test_version(self):
        """
        When run with a version argument, the command prints the flocker version
        and exits with status 0
        """
        runner = CliRunner()
        result = runner.invoke(flocker, ['--version'])
        self.assertEqual(
            (0, u'flocker, version {version}\n'.format(version=__version__)),
            (result.exit_code, result.output)
        )



class FlockerTests(CommonArgumentsTestsMixin, SynchronousTestCase):
    """
    """
    def test_noArguments(self):
        """
        When run without any arguments flocker prints help text.
        """
        assertHelp(self, flocker, [])



class FlockerVolumeTests(CommonArgumentsTestsMixin, SynchronousTestCase):
    """
    """
    def test_subcommand(self):
        """
        L{volume} is registered as a subcommand of L{flocker}.
        """
        runner = CliRunner()
        result = runner.invoke(volume, [])
        self.assertEqual(
            (0, u'\n'),
            (result.exit_code, result.output)
        )


    def test_noArguments(self):
        """
        L{volume} without arguments prints a blank line and exits with status 0.
        """
        runner = CliRunner()
        result = runner.invoke(volume, [])
        self.assertEqual(
            (0, u'\n'),
            (result.exit_code, result.output)
        )


    def test_configDefault(self):
        """
        L{volume} without a config argument passes the default value.
        """
        runner = CliRunner()
        result = runner.invoke(volume, ['--config', 'foo/bar'])
        self.assertEqual(
            (0, u'\n'),
            (result.exit_code, result.output)
        )



# class FilePathTypeTests(SynchronousTestCase):
#     """
#     Tests for L{FilePath} click type.
#     """
#     def test_foo(self):
#         """

#         """
#         self.assertEqual('', FilePath())
