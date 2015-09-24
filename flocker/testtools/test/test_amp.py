# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for :module:`flocker.testtools.amp`.
"""

from ..amp import FakeAMPClient, DelayedAMPClient

from twisted.trial.unittest import SynchronousTestCase

from twisted.protocols.amp import Command, Integer


class TestCommand(Command):
    """
    Trivial command for testing.
    """
    arguments = [
        ('argument', Integer()),
    ]
    response = [
        ('response', Integer()),
    ]


class DelayedAMPClientTests(SynchronousTestCase):
    """
    Tests for :class:`DelayedAMPClient`.
    """

    def test_forwards_call(self):
        """
        Calling :method:`callRemote` forwards the call to the
        underlying client.
        """
        expected_arguments = {'argument': 42}

        client = FakeAMPClient()
        client.register_response(
            TestCommand, expected_arguments, {'response': 7})
        delayed_client = DelayedAMPClient(client)

        delayed_client.callRemote(TestCommand, argument=42)

        self.assertEqual(
            client.calls,
            [(TestCommand, {'argument': 42})],
        )

    def test_delays_response(self):
        """
        The deferred returned by :method:`callRemote` hasn't fired.
        """
        expected_arguments = {'argument': 42}

        client = FakeAMPClient()
        client.register_response(
            TestCommand, expected_arguments, {'response': 7})
        delayed_client = DelayedAMPClient(client)

        d = delayed_client.callRemote(TestCommand, **expected_arguments)

        self.assertNoResult(d)

    def test_forwards_response(self):
        """
        Calling :method:`respond` causes the deferred deferred returned by
        :method:`callRemote` to fire with the result of the underlying client.
        """
        expected_arguments = {'argument': 42}
        expected_response = {'response': 7}
        client = FakeAMPClient()
        client.register_response(
            TestCommand, expected_arguments, expected_response)
        delayed_client = DelayedAMPClient(client)

        d = delayed_client.callRemote(TestCommand, **expected_arguments)

        delayed_client.respond()
        self.assertEqual(
            self.successResultOf(d),
            expected_response,
        )

    # Missing test: Handling of multiple calls.
