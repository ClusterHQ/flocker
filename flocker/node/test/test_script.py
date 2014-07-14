# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for :module:`flocker.node.script`.
"""

from twisted.trial.unittest import SynchronousTestCase
from twisted.python.usage import UsageError
from yaml import safe_dump
from ...testtools import FlockerScriptTestsMixin, StandardOptionsTestsMixin
from ..script import ChangeStateOptions, ChangeStateScript


class ChangeStateScriptTests(FlockerScriptTestsMixin, SynchronousTestCase):
    """
    Tests for L{ChangeStateScript}.
    """
    script = ChangeStateScript
    options = ChangeStateOptions
    command_name = u'flocker-changestate'


class ChangeStateScriptMainTests(SynchronousTestCase):
    """
    Tests for ``ChangeStateScript.main``.
    """

    def test_deferred_result(self):
        """
        ``ChangeStateScript.main`` returns a ``Deferred`` on success.
        """
        script = ChangeStateScript()
        options = ChangeStateOptions()
        dummy_reactor = object()
        self.assertIs(
            None,
            self.successResultOf(script.main(dummy_reactor, options))
        )


class ChangeStateOptionsTests(StandardOptionsTestsMixin, SynchronousTestCase):
    """
    Tests for :class:`ChangeStateOptions`.
    """
    options = ChangeStateOptions

    def test_custom_configs(self):
        """
        The supplied configuration strings are saved as ``dict``\ s on the
        options instance.
        """
        options = self.options()
        expected_deployment = {"foo": "bar", "spam": "eggs", "anumber": 14}
        expected_application = {"appfoo": "appbar",
                                "appspam": "appeggs",
                                "appnumber": 17}
        options.parseOptions(
            [safe_dump(expected_deployment),
             safe_dump(expected_application),
             b'node1.example.com'])

        self.assertDictContainsSubset(
            {'deployment_config': expected_deployment,
             'app_config': expected_application},
            options
        )

    def test_invalid_deployment_configs(self):
        """
        If the supplied deployment_config is not valid `YAML`, a
        ``UsageError`` is raised.
        """
        options = self.options()
        deployment_bad_yaml = "{'foo':'bar', 'x':y, '':'"
        e = self.assertRaises(
            UsageError, options.parseOptions,
            [deployment_bad_yaml, b'', b'node1.example.com'])

        self.assertTrue(
            str(e).startswith('Deployment config could not be parsed as YAML')
        )

    def test_invalid_application_configs(self):
        """
        If the supplied application_config is not valid `YAML`, a
        ``UsageError`` is raised.
        """
        options = self.options()
        application_bad_yaml = "{'foo':'bar', 'x':y, '':'"
        e = self.assertRaises(
            UsageError, options.parseOptions,
            [b'', application_bad_yaml, b'node1.example.com'])

        self.assertTrue(
            str(e).startswith('Application config could not be parsed as YAML')
        )

    def test_hostname_key(self):
        """
        The supplied hostname is assigned to a `hostname` key.
        """
        expected_hostname = u'foobar.example.com'
        options = self.options()
        options.parseOptions([b'{}', b'{}', expected_hostname.encode('ascii')])
        self.assertEqual(
            (expected_hostname, unicode),
            (options['hostname'], type(options['hostname']))
        )

    def test_nonascii_hostname(self):
        """
        A ``UsageError`` is raised if the supplied hostname is not ASCII
        encoded.
        """
        hostname = u'\xa3'.encode('utf8')
        options = self.options()
        e = self.assertRaises(
            UsageError,
            options.parseOptions, [b'{}', b'{}', hostname])

        self.assertEqual(
            "Non-ASCII hostname: {hostname}".format(hostname=hostname),
            str(e)
        )
