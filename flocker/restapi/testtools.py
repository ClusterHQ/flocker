# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Public utilities for testing code that uses the REST API.
"""

__all__ = ["buildIntegrationTests", "dumps",
           "loads", "dummyRequest", "CloseEnoughJSONResponse",
           "CloseEnoughResponse",
           "extractSuccessfulJSONResult", "render", "asResponse",
           "build_schema_test"]


from io import BytesIO
from json import dumps, loads as _loads
from itertools import count

from jsonschema.exceptions import ValidationError

from zope.interface import implementer

from twisted.python.log import err
from twisted.web.iweb import IAgent, IResponse
from twisted.internet.endpoints import TCP4ClientEndpoint
from twisted.internet import defer
from twisted.web.client import ProxyAgent, readBody
from twisted.web.server import NOT_DONE_YET, Site
from twisted.web.resource import getChildForRequest
from twisted.trial.unittest import SynchronousTestCase, TestCase
from twisted.web.http import urlparse, unquote
from twisted.internet.address import IPv4Address
from twisted.test.proto_helpers import StringTransport
from twisted.web.client import ResponseDone
from twisted.internet.interfaces import IPushProducer
from twisted.python.failure import Failure
from twisted.internet import reactor
from twisted.web.http_headers import Headers

from flocker.restapi._schema import getValidator


def loads(s):
    try:
        return _loads(s)
    except Exception as e:
        # Turn the decoding exception into something with more useful
        # information.
        raise Exception(
            "Failed to decode response %r: %s" % (s, e))


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

    def getResult(data):
        if response.code > 299:
            raise AssertionError((response.code, data))
        return data
    result.addCallback(getResult)
    return result


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
        Tests that endpoints are available over the network interfaces that
        real API users will be connecting from.
        """
        def setUp(self):
            self.app = fixture(self)
            self.port = reactor.listenTCP(
                0, Site(self.app.resource()),
                interface=b"127.0.0.1",
            )
            self.addCleanup(self.port.stopListening)
            portno = self.port.getHost().port
            self.agent = ProxyAgent(
                TCP4ClientEndpoint(
                    reactor, "127.0.0.1", portno,
                ),
                reactor
            )
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
    def __init__(self, version, code, phrase, headers, request,
                 previousResponse, responseBody):
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


def build_schema_test(name, schema, schema_store,
                      failing_instances, passing_instances):
    """
    Create test case verifying that various instances pass and fail
    verification with a given JSON Schema.

    :param bytes name: Name of test case to create.
    :param dict schema: Schema to test.
    :param dict schema_store: The schema definitions.
    :param list failing_instances: Instances which should fail validation.
    :param list passing_instances: Instances which should pass validation.

    :returns: The test case; a ``SynchronousTestCase`` subclass.
    """
    body = {
        'schema': schema,
        'schema_store': schema_store,
        'validator': getValidator(schema, schema_store),
        'passing_instances': passing_instances,
        'failing_instances': failing_instances,
        }
    for i, inst in enumerate(failing_instances):
        def test(self, inst=inst):
            self.assertRaises(ValidationError,
                              self.validator.validate, inst)
        test.__name__ = 'test_fails_validation_%d' % (i,)
        body[test.__name__] = test

    for i, inst in enumerate(passing_instances):
        def test(self, inst=inst):
            self.validator.validate(inst)
        test.__name__ = 'test_passes_validation_%d' % (i,)
        body[test.__name__] = test

    return type(name, (SynchronousTestCase, object), body)
