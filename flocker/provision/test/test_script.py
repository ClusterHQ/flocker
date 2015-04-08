# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

from StringIO import StringIO

from twisted.trial.unittest import TestCase, SynchronousTestCase
from ...testtools import FlockerScriptTestsMixin, StandardOptionsTestsMixin
from ..script import ProvisionScript, ProvisionOptions


class FlockerProvisionTests(FlockerScriptTestsMixin, TestCase):
    """Tests for ``flocker-provision`` CLI."""
    script = ProvisionScript
    options = ProvisionOptions
    command_name = u'flocker-provision'


class FlockerProvisionOptionsTests(
        StandardOptionsTestsMixin, SynchronousTestCase):
    """Tests for :class:`ProvisionOptions`."""
    options = ProvisionOptions


class FlockerCLIMainTests(TestCase):
    """ProvisionScript.main``.
    """
    def test_deferred_result(self):
        """
        ``ProvisionScript.main`` returns a ``Deferred`` on success.
        """
        options = ProvisionOptions()
        options.parseOptions([])

        script = ProvisionScript()
        dummy_reactor = object()

        self.assertEqual(
            None,
            self.successResultOf(script.main(dummy_reactor, options))
        )

class CreateOptionsTests(SynchronousTestCase):
    """
    Tests for ``CreateOptions``.
    """

    def test_username_required(self):
        """
        The ``--user-name`` option is required.
        """
        options = CreateOptions()
        self.assertRaises(
            UsageError, options.parseOptions,
            ['--driver', 'rackspace',
             '--api-key', 'api-key',
             '--region', 'region',
             '--ssh-key-name', 'key-name'])

    def test_api_key_required(self):
        """
        The ``--api-key`` option is required.
        """
        options = CreateOptions()
        self.assertRaises(
            UsageError, options.parseOptions,
            ['--driver', 'rackspace',
             '--username', 'username',
             '--region', 'region',
             '--ssh-key-name', 'key-name'])

    def test_region_required(self):
        """
        The ``--region`` option is required.
        """
        options = CreateOptions()
        self.assertRaises(
            UsageError, options.parseOptions,
            ['--driver', 'rackspace',
             '--username', 'username',
             '--api-key', 'api-key',
             '--ssh-key-name', 'key-name'])

    def test_ssh_key_name_required(self):
        """
        The ``--ssh-key-name`` option is required.
        """
        options = CreateOptions()
        self.assertRaises(
            UsageError, options.parseOptions,
            ['--driver', 'rackspace',
             '--username', 'username',
             '--api-key', 'api-key',
             '--region', 'region'])

    def test_num_agent_nodes_optional(self):
        """
        The ``--num-agent-nodes`` option is required.
        """
        options = CreateOptions()
        self.assertRaises(
            UsageError, options.parseOptions,
            ['--driver', 'rackspace',
             '--username', 'username',
             '--api-key', 'api-key',
             '--region', 'region',
             '--ssh-key-name', 'key-name'])

    def test_zero_nodes(self):
        """
        Passing ``0`` to ``--num-agent-nodes`` option displays an error .
        """
        options = CreateOptions()
        self.assertRaises(
            UsageError, options.parseOptions,
            ['--driver', 'rackspace',
             '--username', 'username',
             '--api-key', 'api-key',
             '--region', 'region',
             '--ssh-key-name', 'key-name',
             '--num-agent-nodes', '0')

    def test_negative_nodes(self):
        """
        Passing ``-1`` to ``--num-agent-nodes`` option displays an error .
        """
        options = CreateOptions()
        self.assertRaises(
            UsageError, options.parseOptions,
            ['--driver', 'rackspace',
             '--username', 'username',
             '--api-key', 'api-key',
             '--region', 'region',
             '--ssh-key-name', 'key-name',
             '--num-agent-nodes', '-1')


class CreateTests(SynchronousTestCase):
    """
    Tests for ``create``.
    """
    # TODO do and test logging as a follow-up
    # log to a file

    def test_progress_report(self):
        """
        A progress report is displayed.
        """

    def test_provision(self):
        """
        Provisioned nodes' IP addresses are displayed for CentOS 7 nodes on
        Rackspace.
        """
        reactor = MemoryReactor()
        output = StringIO()
        error = StringIO()
        provisioner = MemoryProvisioner()
        d = create(
            reactor, provisioner=provisioner, num_agent_nodes=3,
            output=output, error=error)
        self.successResultOf(d)
        self.assertEqual(
            [output.getvalue(), error.getvalue()],
            [dedent("""\
                control_node: 192.0.2.1
                agent_nodes:
                - 192.0.2.2
                - 192.0.2.3
                - 192.0.2.4
                """),
             dedent("""\
                 Creating node 0: flocker-provisioning-script-0
                 Creating node 1: flocker-provisioning-script-1
                 Creating node 2: flocker-provisioning-script-2
                 Creating node 3: flocker-provisioning-script-3
                 """)


    def test_num_nodes(self):
        """
        The number of nodes specified are created.
        """
        reactor = MemoryReactor
        create
        pass

    def test_provisioning_fails(self):
        """
        If provisioning the node fails, an error message is shown.
        """
        pass

    def _test_control_node(self):
        """
        The node shown to be the control node is the control node.
        """
        pass
