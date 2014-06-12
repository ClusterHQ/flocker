# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for :module:`flocker.script`.
"""

from __future__ import absolute_import

import sys
import io

from twisted.trial.unittest import SynchronousTestCase
from twisted.application.service import IServiceMaker, IServiceCollection
from twisted.plugin import getPlugins
from zope.interface.verify import verifyObject

from click.testing import CliRunner

from ..script import flocker, volume, FlockerVolumeOptions
from .. import __version__


def assertClickHelp(testCase, command, arguments):
    """
    Assert that help text is printed.
    """
    runner = CliRunner()
    result = runner.invoke(command, arguments)

    testCase.assertEqual(
        (None, 0, u'Usage'),
        (result.exception, result.exit_code, result.output[:len(u'Usage')])
    )



def assertClickOutput(testCase, result, expectedOutput, expectedStatus=0):
    """
    Assert that the expected output is printed and that no unexpected
    exceptions were raised.

    XXX: This is required because of the way click.testing.CliRunner
    captures exceptions. See https://github.com/mitsuhiko/click/issues/136
    """
    testCase.assertEqual(
        (None, expectedOutput, expectedStatus),
        (result.exception, result.output, result.exit_code)
    )



class CommonArgumentsTestsMixin(object):
    def test_help(self):
        """
        When run with a help argument, the flocker prints help text and exits
        with status 0.
        """
        assertClickHelp(self, flocker, ['--help'])


    def test_version(self):
        """
        When run with a version argument, the command prints the flocker version
        and exits with status 0
        """
        runner = CliRunner()
        result = runner.invoke(flocker, ['--version'])
        assertClickOutput(
            self, result,
            u'flocker, version {version}\n'.format(version=__version__),
            0
        )



class FlockerTests(CommonArgumentsTestsMixin, SynchronousTestCase):
    """
    """
    def test_noArguments(self):
        """
        When run without any arguments flocker prints help text.
        """
        assertClickHelp(self, flocker, [])



class FlockerVolumeTests(CommonArgumentsTestsMixin, SynchronousTestCase):
    """
    """
    def test_subcommand(self):
        """
        L{volume} is registered as a subcommand of L{flocker}.
        """
        runner = CliRunner()
        result = runner.invoke(flocker, ['volume'])
        assertClickOutput(self, result, u'\n', 0)


    def test_noArguments(self):
        """
        L{volume} without arguments prints a blank line and exits with status 0.
        """
        runner = CliRunner()
        result = runner.invoke(volume, [])
        assertClickOutput(self, result, u'\n', 0)


    def test_configDefault(self):
        """
        L{volume} without a config argument passes the default value.
        """
        runner = CliRunner()
        result = runner.invoke(volume)
        assertClickOutput(self, result, b'\n', 0)



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
