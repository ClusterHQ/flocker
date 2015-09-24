# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for :module:`flocker.testtools.amp`.
"""

from ..amp import FakeAMPClient, DelayedAMPClient
from ...control.test.test_protocol import LoopbackAMPClient

from twisted.trial.unittest import SynchronousTestCase

from twisted.protocols.amp import (
    Command, Integer, ListOf, MAX_VALUE_LENGTH, TooLong, CommandLocator,
)


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


class CommandWithBigListArgument(Command):
    arguments = [
        ("big", ListOf(Integer())),
    ]


class CommandWithBigListArgumentLocator(CommandLocator):
    @CommandWithBigListArgument.responder
    def responder(self, big):
        return {}


class LoopbackAMPClientTests(SynchronousTestCase):
    """
    Tests for :class:`LoopbackAMPClient`.
    """
    def test_regular_argument(self):
        """
        ``LoopbackAMPClient.callRemote`` can serialize arguments that are <
        MAX_VALUE_LENGTH.
        """
        client = LoopbackAMPClient(
            command_locator=CommandWithBigListArgumentLocator()
        )

        d = client.callRemote(
            command=CommandWithBigListArgument,
            big=range(10),
        )
        self.successResultOf(d)

    def test_long_argument(self):
        """
        ``LoopbackAMPClient.callRemote`` raises ``TooLong`` when supplied with
        a command argument which is > MAX_VALUE_LENGTH when serialized.
        """
        client = LoopbackAMPClient(
            command_locator=CommandWithBigListArgumentLocator()
        )
        self.assertRaises(
            TooLong,
            client.callRemote,
            command=CommandWithBigListArgument,
            # A list containing all integers up to MAX_VALUE_LENGTH must be
            # longer than MAX_VALUE_LENGTH when serialized.
            big=range(MAX_VALUE_LENGTH),
        )
