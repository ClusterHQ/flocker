"""
Utilities for testing REST APIs.
"""

from io import BytesIO
from base64 import b64encode
from json import dumps, loads as _loads
from itertools import count

from klein import Klein
from klein.resource import KleinResource

from netifaces import interfaces as networkInterfaces, ifaddresses, AF_INET

from zope.interface import implementer

from twisted.python.log import err
from twisted.web.iweb import IAgent, IResponse
from twisted.internet.endpoints import TCP4ClientEndpoint
from twisted.web.http_headers import Headers
from twisted.web.client import ProxyAgent, FileBodyProducer, readBody
from twisted.web.server import NOT_DONE_YET, Site
from twisted.web.resource import getChildForRequest
from twisted.internet import defer
from twisted.trial.unittest import TestCase, SkipTest
from twisted.web.http import urlparse, unquote
from twisted.internet.address import IPv4Address
from twisted.test.proto_helpers import StringTransport
from twisted.web.client import ResponseDone
from twisted.internet.interfaces import IPushProducer
from twisted.python.failure import Failure
from twisted.internet import reactor

from eliot.testing import LoggedMessage, LoggedAction, assertContainsFields

from .._logging import REQUEST


# Make it possible to unit test Klein.  Without being able to compare these
# objects for equality, it's difficult to write good assertions for the return
# value of APIRealm.requestAvatar.
# https://github.com/twisted/klein/pull/45
def __eq__(self, other):
    if not isinstance(other, Klein):
        return NotImplemented
    return vars(self) == vars(other)
Klein.__eq__ = __eq__
del __eq__

def __eq__(self, other):
    if not isinstance(other, KleinResource):
        return NotImplemented
    return vars(self) == vars(other)
KleinResource.__eq__ = __eq__
del __eq__


def loads(s):
    try:
        return _loads(s)
    except Exception as e:
        # Turn the decoding exception into something with more useful
        # information.
        raise Exception(
            "Failed to decode response %r: %s" % (s, e))



FAILED_INPUT_VALIDATION = u"The provided JSON doesn't match the required schema."




def goodResult(result):
    """
    Construct the boilerplate structure around an application-specified result
    object for a successful API response.
    """
    return {u"error": False, u"result": result}



def badResult(result):
    """
    Construct the boilerplate structure around an application-specified result
    object for an error API response.
    """
    return {u"error": True, u"result": result}



class CloseEnoughResponse(object):
    """
    A helper for verifying that an HTTP response matches certain requirements.

    @ivar decode: A one-argument callable which is used to turn the response
        body into a structured object suitable for comparison against the
        expected body.
    """
    decode = staticmethod(lambda body: body)

    def __init__(self, code, headers, body):
        """
        @param code: The expected HTTP response code.
        @type code: L{int}

        @param headers: The minimum set of headers which must be present in the
            response.
        @type headers: L{twisted.web.http_headers.Headers}

        @param body: The structured form of the body expected in the response.
            This is compared against the received body after the received body
            is decoded with C{self.decode}.
        """
        self.code = code
        self.headers = headers
        self.body = body


    def verify(self, response):
        """
        Check the given response against the requirements defined by this
        instance.

        @param response: The response to check.
        @type response: L{twisted.web.iweb.IResponse}

        @return: A L{Deferred} that fires with C{None} after the response has
            been found to satisfy all the requirements or that fires with a
            L{Failure} if any part of the response is incorrect.
        """
        reading = readBody(response)
        reading.addCallback(self.decode)
        reading.addCallback(self._verifyWithBody, response)
        return reading


    def _verifyWithBody(self, body, response):
        """
        Do the actual comparison.

        @param body: The response body.
        @type body: L{bytes}

        @param response: The response object.
        @type response: L{twisted.web.iweb.IResponse}

        @raise: If the response fails to meet any of the requirements.

        @return: If the response meets all the requirements, C{None}.
        """
        problems = []

        if self.code != response.code:
            problems.append(
                "response code: %r != %r" % (self.code, response.code))

        for name, expected in self.headers.getAllRawHeaders():
            received = response.headers.getRawHeaders(name)
            if expected != received:
                problems.append(
                    "header %r: %r != %r" % (name, expected, received))

        if self.body != body:
            problems.append("body: %r != %r" % (self.body, body))

        if problems:
            raise Exception("\n    ".join([""] + problems))



class CloseEnoughJSONResponse(CloseEnoughResponse):
    """
    A helper for verifying HTTP responses containing JSON-encoded bodies.

    @see: L{CloseEnoughResponse}
    """
    decode = staticmethod(loads)



def extractSuccessfulJSONResult(response):
    """
    Extract a successful API result from a HTTP response.

    @param response: The response to check.
    @type response: L{twisted.web.iweb.IResponse}

    @return: L{Deferred} that fires with the result part of the decoded JSON.

    @raises L{AssertionError}: If the response is not a successful one.
    """
    result = readBody(response)
    result.addCallback(loads)
    def getResult(dictionary):
        if dictionary[u"error"]:
            raise AssertionError(dictionary)
        return dictionary[u"result"]
    result.addCallback(getResult)
    return result



def _assertRequestLogged(path):
    def actuallyAssert(self, logger):
        request = LoggedAction.ofType(logger.messages, REQUEST)[0]
        assertContainsFields(self, request.startMessage, {
                u"request_path": repr(path).decode("ascii"),
                })
    return actuallyAssert



def _assertTracebackLogged(exceptionType):
    def _assertTracebackLogged(self, logger):
        """
        Assert that a traceback for an L{ArbitraryException} was logged as a
        child of a L{REQUEST} action.
        """
        # Get rid of it so it doesn't fail the test later.
        tracebacks = logger.flushTracebacks(exceptionType)
        if len(tracebacks) > 1:
            self.fail("Multiple tracebacks: %s" % tracebacks)
        traceback = tracebacks[0]

        # Verify it contains what it's supposed to contain.
        assertContainsFields(self, traceback, {
                u"exception": exceptionType,
                u"message_type": u"eliot:traceback",
                # Just assume the traceback it contains is correct.  The code
                # that generates that string isn't part of this unit, anyway.
                })

        # Verify that it is a child of one of the request actions.
        for request in LoggedAction.ofType(logger.messages, REQUEST):
            if LoggedMessage(traceback) in request.descendants():
                break
        else:
            self.fail(
                "Traceback was logged outside of the context of a request "
                "action.")

    return _assertTracebackLogged



def authenticatedRequest(agent, user, method, uri, parameters):
    """
    Issue a request with I{Basic} authentication headers.

    @param agent: An L{IAgent} to use to issue the request.

    @param user: The L{UsernamePassword} instance representing the credentials
        to include.

    @param method: See L{IAgent.request}
    @param uri: See L{IAgent.request}

    @param parameters: An object to JSON encode and send in the request body.

    @return: A L{Deferred} that fires with an L{IResponse} provider.
    """
    body = FileBodyProducer(BytesIO(dumps(parameters)))
    authorization = b64encode(b"%s:%s" % (user.username, user.password))
    headers = Headers({
            b"authorization": [b"Basic " + authorization],
            b"content-type": [b"application/json"],
            })

    return agent.request(method, uri, headers, body)



def responseCredentials(requestCredentials):
    """
    Get a list of credentials which can be expected in an API response.

    @param requestCredentials: The complete credentials which were previously
        submitted and from which the response credentials can be expected to be
        derived.
    @type param: L{list} of L{dict}

    @return: The filtered credentials.
    @rtype: L{list} of L{dict}
    """
    return [
        cred for cred in requestCredentials
        if "ssh_public_key" in cred]



class _anything(object):
    """
    An instance of this class compares equal to any other object.
    """
    def __eq__(self, other):
        return True

    def __ne__(self, other):
        return False

anything = _anything()



class _incident(object):
    """
    An instance of this class compares equal to the kind of L{dict} which
    represents an error response from the API.

    Such a L{dict} has an C{u"error"} key with a C{True} value and a
    C{u"result"} key with a L{unicode} value.
    """
    def __eq__(self, other):
        return (
            isinstance(other, dict) and
            set(other) == {u"error", u"result"} and
            other[u"error"] is True and
            isinstance(other[u"result"], unicode)
            )


    def __ne__(self, other):
        return not self.__eq__(other)

incident = _incident()




def buildIntegrationTests(mixinClass, name, fixture):
    """
    Build L{TestCase} classes that runs the tests in the mixin class with both
    real and in-memory queries.

    @param mixinClass: A mixin class for L{TestCase} that relies on having a
        C{self.scenario}.

    @param name: A C{str}, the name of the test category.

    :param fixture: A callable that takes a ``TestCase`` and returns a
        ``klein.Klein`` object.

    @return: A pair of L{TestCase} classes.
    """
    class RealTests(mixinClass, TestCase):
        """
        Tests that endpoints are available over the network interfaces that real
        API users will be connecting from.
        """
        def setUp(self):
            self.app = fixture(self)
            self.port = reactor.listenTCP(0, Site(self.app.resource()),
                                          interface="127.0.0.1")
            self.addCleanup(self.port.stopListening)
            portno = self.port.getHost().port
            self.agent = ProxyAgent(
                TCP4ClientEndpoint(reactor, "127.0.0.1", portno),
                reactor)
            super(RealTests, self).setUp()


    class MemoryTests(mixinClass, TestCase):
        """
        Tests that endpoints are available in the appropriate place, without
        testing that the correct network interfaces are listened on.
        """
        def setUp(self):
            self.app = fixture(self)
            self.agent = MemoryAgent(self.app.resource())
            super(MemoryTests, self).setUp()


    RealTests.__name__ += name
    MemoryTests.__name__ += name
    RealTests.__module__ = mixinClass.__module__
    MemoryTests.__module__ = mixinClass.__module__
    return RealTests, MemoryTests


# Fakes for testing Twisted Web servers.  Unverified.  Belongs in Twisted.
# https://twistedmatrix.com/trac/ticket/3274
from twisted.web.server import Request
from twisted.web.http import HTTPChannel


class EventChannel(object):
    """
    An L{EventChannel} provides one-to-many event publishing in a
    re-usable container.

    Any number of parties may subscribe to an event channel to receive
    the very next event published over it.  A subscription is a
    L{Deferred} which will get the next result and is then no longer
    associated with the L{EventChannel} in any way.

    Future events can be received by re-subscribing to the channel.

    @ivar _subscriptions: A L{list} of L{Deferred} instances which are waiting
        for the next event.
    """
    def __init__(self):
        self._subscriptions = []


    def _itersubscriptions(self):
        """
        Return an iterator over all current subscriptions after
        resetting internal subscription state to forget about all of
        them.
        """
        subscriptions = self._subscriptions[:]
        del self._subscriptions[:]
        return iter(subscriptions)


    def callback(self, value):
        """
        Supply a success value for the next event which will be published now.
        """
        for subscr in self._itersubscriptions():
            subscr.callback(value)


    def errback(self, reason=None):
        """
        Supply a failure value for the next event which will be published now.
        """
        for subscr in self._itersubscriptions():
            subscr.errback(reason)


    def subscribe(self):
        """
        Get a L{Deferred} which will fire with the next event on this channel.

        @rtype: L{Deferred}
        """
        d = defer.Deferred(canceller=self._subscriptions.remove)
        self._subscriptions.append(d)
        return d


class _DummyRequest(Request):

    # Request has code and code_message attributes.  They're not part of
    # IRequest.  A bunch of existing code written against _DummyRequest used
    # the _code and _message attributes previously provided by _DummyRequest
    # (at least those names look like they're not part of the interface).
    # Preserve those attributes here but avoid re-implementing setResponseCode
    # or duplicating the state Request is keeping.
    @property
    def _code(self):
        return self.code


    @property
    def _message(self):
        return self.code_message


    def __init__(self, counter, method, path, headers, content):

        channel = HTTPChannel()
        host = IPv4Address(b"TCP", b"127.0.0.1", 80)
        channel.makeConnection(StringTransport(hostAddress=host))

        Request.__init__(self, channel, False)

        # An extra attribute for identifying this fake request
        self._counter = counter

        # Attributes a Request is supposed to have but we have to set ourselves
        # because the base class mixes together too much other logic with the
        # code that sets them.
        self.prepath = []
        self.requestHeaders = headers
        self.content = BytesIO(content)

        self.requestReceived(method, path, b"HTTP/1.1")

        # requestReceived initializes the path attribute for us (but not
        # postpath).
        self.postpath = list(map(unquote, self.path[1:].split(b'/')))


        # Our own notifyFinish / finish state because the inherited
        # implementation wants to write confusing stuff to the transport when
        # the request gets finished.
        self._finished = False
        self._finishedChannel = EventChannel()

        # Our own state for the response body so we don't have to dig it out of
        # the transport.
        self._responseBody = b""


    def process(self):
        """
        Don't do any processing.  Override the inherited implementation so it
        doesn't do any, either.
        """


    def finish(self):
        self._finished = True
        self._finishedChannel.callback(None)


    def notifyFinish(self):
        return self._finishedChannel.subscribe()


    # Not part of the interface but called by DeferredResource, used by
    # twisted.web.guard (therefore important to us)
    def processingFailed(self, reason):
        err(reason, "Processing _DummyRequest %d failed" % (self._counter,))


    def write(self, data):
        self._responseBody += data


    def render(self, resource):
        # TODO: Required by twisted.web.guard but not part of IRequest ???
        render(resource, self)



def asResponse(request):
    """
    Extract the response data stored on a request and create a real response
    object from it.

    @param request: A L{_DummyRequest} that has been rendered.

    @return: An L{IResponse} provider carrying all of the response information
        that was rendered onto C{request}.
    """
    return _MemoryResponse(
        b"HTTP/1.1", request.code, request.code_message,
        request.responseHeaders, None, None,
        request._responseBody)



@implementer(IResponse)
class _MemoryResponse(object):
    """
    An entirely in-memory response to an HTTP request. This is not tested
    because it should be moved to Twisted.
    """
    def __init__(self, version, code, phrase, headers, request, previousResponse, responseBody):
        """
        @see: L{IResponse}

        @param responseBody: The body of the response.
        @type responseBody: L{bytes}
        """
        self.version = version
        self.code = code
        self.phrase = phrase
        self.headers = headers
        self.request = request
        self.length = len(responseBody)
        self._responseBody = responseBody
        self.setPreviousResponse(previousResponse)


    def deliverBody(self, protocol):
        """
        Immediately deliver the entire response body to C{protocol}.
        """
        protocol.makeConnection(_StubProducer())
        protocol.dataReceived(self._responseBody)
        protocol.connectionLost(Failure(ResponseDone()))


    def setPreviousResponse(self, response):
        self.previousResponse = response



@implementer(IPushProducer)
class _StubProducer(object):
    """
    A do-nothing producer that L{_MemoryResponse} can use while
    delivering response bodies.
    """
    def pauseProducing(self):
        pass


    def resumeProducing(self):
        pass


    def stopProducing(self):
        pass


@implementer(IAgent)
class MemoryAgent(object):
    """
    L{MemoryAgent} generates responses to requests by rendering an
    L{IResource} using those requests.

    @ivar resource: The root resource from which traversal for request
        dispatching/response starts.
    @type resource: L{IResource} provider
    """
    def __init__(self, resource):
        self.resource = resource


    def request(self, method, url, headers=None, body=None):
        """
        Find the child of C{self.resource} for the given request and
        render it to generate a response.
        """
        if headers is None:
            headers = Headers()

        # Twisted Web server only supports dispatching requests after reading
        # the entire request body into memory.
        content = BytesIO()
        if body is None:
            reading = defer.succeed(None)
        else:
            reading = body.startProducing(content)
        def finishedReading(ignored):
            request = dummyRequest(method, url, headers, content.getvalue())
            resource = getChildForRequest(self.resource, request)
            d = render(resource, request)
            d.addCallback(lambda ignored: request)
            return d
        rendering = reading.addCallback(finishedReading)

        def rendered(request):
            return _MemoryResponse(
                (b"HTTP", 1, 1),
                request._code,
                request._message,
                request.responseHeaders,
                request,
                None,
                request._responseBody)
        rendering.addCallback(rendered)
        return reading



_dummyRequestCounter = iter(count())
def dummyRequest(method, path, headers, body=b""):
    """
    Construct a new dummy L{IRequest} provider.

    @param method: The HTTP method of the request.  For example, C{b"GET"}.
    @type method: L{bytes}

    @param path: The encoded path part of the URI of the request.  For example,
        C{b"/foo"}.
    @type path: L{bytes}

    @param headers: The headers of the request.
    @type headers: L{Headers}

    @param body: The bytes that make up the request body.
    @type body: L{bytes}

    @return: A L{IRequest} which can be used to render an L{IResource} using
        only in-memory data structures.
    """
    scheme, location, path, params, query, fragment = urlparse(path)
    if query:
        # Oops, dropped params.  Good thing no one cares.
        path = path + "?" + query
    return _DummyRequest(
        next(_dummyRequestCounter),
        method, path, headers, body)



def render(resource, request):
    """
    Render an L{IResource} using a particular L{IRequest}.

    @raise ValueError: If L{IResource.render} returns an unsupported value.

    @return: A L{Deferred} that fires with C{None} when the response has been
        completely rendered.
    """
    result = resource.render(request)
    if isinstance(result, bytes):
        request.write(result)
        request.finish()
        return defer.succeed(None)
    elif result is NOT_DONE_YET:
        if request._finished:
            return defer.succeed(None)
        else:
            return request.notifyFinish()
    else:
        raise ValueError("Unexpected return value: %r" % (result,))


# Unfortunately Klein imposes this strange requirement that the request object
# be adaptable to KleinRequest.  Klein only registers an adapter from
# twisted.web.server.Request - despite the fact that the adapter doesn't
# actually use the adaptee for anything.
#
# Here, register an adapter from the dummy request type so that tests can
# exercise Klein-based code without trying to use the real request type.
#
# See https://github.com/twisted/klein/issues/31
from twisted.python.components import registerAdapter
from klein.app import KleinRequest
from klein.interfaces import IKleinRequest
registerAdapter(KleinRequest, _DummyRequest, IKleinRequest)
