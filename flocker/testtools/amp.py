# Copyright ClusterHQ Inc.  See LICENSE file for details.
# -*- test-case-name: flocker.testtools.test.test_amp -*-

"""
Fakes for interacting with AMP.
"""

from twisted.python.failure import Failure
from twisted.internet.defer import Deferred, succeed
from twisted.internet.error import ConnectionLost
from twisted.protocols.amp import (
    AMP, InvalidSignature,
    RemoteAmpError, UnknownRemoteError, parseString,
)
from twisted.test.proto_helpers import StringTransport

__all__ = [
    'StringTransportWithAbort',
    'FakeAMPClient',
    'DelayedAMPClient',
    'LoopbackAMPClient',
]


class StringTransportWithAbort(StringTransport):
    """
    A ``StringTransport`` that implements ``abortConnection``.
    """
    def __init__(self, *args, **kwargs):
        self.aborted = False
        StringTransport.__init__(self, *args, **kwargs)

    def abortConnection(self):
        self.aborted = True
        self.connected = False


class FakeAMPClient(object):
    """
    Emulate an AMP client's ability to send commands.

    A minimal amount of validation is done on registered responses and sent
    requests, but this should not be relied upon.

    :ivar list calls: ``(command, kwargs)`` tuples of commands that have
        been sent using ``callRemote``.
    """

    def __init__(self):
        """
        Initialize a fake AMP client.
        """
        self._responses = {}
        self.calls = []

    def _makeKey(self, command, kwargs):
        """
        Create a key for the responses dictionary.

        @param commandType: a subclass of C{amp.Command}.

        @param kwargs: a dictionary.

        @return: A value that can be used as a dictionary key.
        """
        return (command, tuple(sorted(kwargs.items())))

    def register_response(self, command, kwargs, response):
        """
        Register a response to a L{callRemote} command.

        @param commandType: a subclass of C{amp.Command}.

        @param kwargs: Keyword arguments taken by the command, a C{dict}.

        @param response: The response to the command.
        """
        if isinstance(response, Exception):
            response = Failure(response)
        else:
            try:
                command.makeResponse(response, AMP())
            except KeyError:
                raise InvalidSignature("Bad registered response")
        self._responses[self._makeKey(command, kwargs)] = response

    def callRemote(self, command, **kwargs):
        """
        Return a previously registered response.

        @param commandType: a subclass of C{amp.Command}.

        @param kwargs: Keyword arguments taken by the command, a C{dict}.

        @return: A C{Deferred} that fires with the registered response for
            this particular combination of command and arguments.
        """
        self.calls.append((command, kwargs))
        command.makeArguments(kwargs, AMP())
        # if an eliot_context is present, disregard it, because we cannot
        # reliably determine this in advance in order to include it in the
        # response register
        if 'eliot_context' in kwargs:
            kwargs.pop('eliot_context')
        return succeed(self._responses[self._makeKey(command, kwargs)])


class DelayedAMPClient(object):
    """
    A wrapper for ``FakeAMPClient`` that allows responses to be delayed.

    :ivar _client: The underlying AMP client.
    :ivar _calls: List of tuples of deferred and response.
    """

    def __init__(self, client):
        self._client = client
        self._calls = []
        self.transport = StringTransport()

    def callRemote(self, command, **kwargs):
        """
        Call the underlying AMP client, and delay the response until
        :method:`respond` is called.

        @param commandType: a subclass of C{amp.Command}.

        @param kwargs: Keyword arguments taken by the command, a C{dict}.

        @return: A C{Deferred} that fires when :method:`respond` is called,
            with the response from the underlying cleint.
        """
        d = Deferred()
        response = self._client.callRemote(command, **kwargs)
        self._calls.append((d, response))
        return d

    def respond(self):
        """
        Respond to the oldest outstanding remote call.
        """
        d, response = self._calls.pop(0)
        response.chainDeferred(d)


def connected_amp_protocol():
    """
    :return: ``AMP`` hooked up to transport.
    """
    p = AMP()
    p.makeConnection(StringTransport())
    return p


class LoopbackAMPClient(object):
    """
    Allow sending commands, in-memory, to an AMP command locator.
    """
    def __init__(self, command_locator):
        """
        :param command_locator: A ``CommandLocator`` instance that
            will handle commands sent using ``callRemote``.
        """
        self._locator = command_locator
        self.transport = StringTransportWithAbort()

    def callRemote(self, command, **kwargs):
        """
        Call the corresponding responder on the configured locator.

        @param commandType: a subclass of L{AMP_MODULE.Command}.

        @param kwargs: Keyword arguments taken by the command, a C{dict}.

        @return: A C{Deferred} that fires with the result of the responder.
        """
        # Get a Box for the supplied arguments. E.g.
        # command = ClusterStatusUpdate
        # kwargs = {"configuration": Deployment(nodes={Node(...)})}
        # The Box contains the Deployment object converted to nested dict. E.g.
        # Box({"configuration": {"$__class__$": "Deployment", ...}})
        argument_box = command.makeArguments(kwargs, self._locator)

        # Serialize the arguments to prove that we can.  For example, if an
        # argument would serialize to more than 64kB then we can't actually
        # serialize it so we want a test attempting this to fail.
        # Wire format will contain bytes. E.g.
        # b"\x12\x32configuration..."
        wire_format = argument_box.serialize()

        # Now decode the bytes back to a Box
        [decoded_argument_box] = parseString(wire_format)

        # And supply that to the responder which internally reverses
        # makeArguments -> back to kwargs
        responder = self._locator.locateResponder(command.commandName)
        d = responder(decoded_argument_box)

        def serialize_response(response_box):
            # As above, prove we can serialize the response.
            wire_format = response_box.serialize()
            [decoded_response_box] = parseString(wire_format)
            return decoded_response_box

        d.addCallback(serialize_response)
        d.addCallback(command.parseResponse, self._locator)

        def massage_error(error):
            if error.check(RemoteAmpError):
                rje = error.value
                errorType = command.reverseErrors.get(
                    rje.errorCode, UnknownRemoteError)
                return Failure(errorType(rje.description))

            # In this case the actual AMP implementation closes the connection.
            # Weakly simulate that here by failing how things fail if the
            # connection closes and commands are outstanding.  This is sort of
            # terrible behavior but oh well.  https://tm.tl/7055
            return Failure(ConnectionLost(str(error)))

        d.addErrback(massage_error)
        return d
