# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
Tests for ``flocker.restapi._infrastructure``.
"""

from jsonschema.exceptions import ValidationError
from klein import Klein

from twisted.python.constants import Names, NamedConstant
from twisted.python.failure import Failure
from twisted.internet.defer import succeed, fail
from twisted.web.http_headers import Headers
from twisted.web.http import (
    BAD_REQUEST, INTERNAL_SERVER_ERROR, PAYMENT_REQUIRED, GONE,
    NOT_ALLOWED, NOT_FOUND)

from twisted.trial.unittest import SynchronousTestCase

from .._infrastructure import (
    EndpointResponse, user_documentation, structured)
from .._logging import REQUEST
from .._error import (
    ILLEGAL_CONTENT_TYPE_DESCRIPTION, DECODING_ERROR_DESCRIPTION,
    BadRequest)


from eliot.testing import validateLogging, LoggedAction

from ..testtools import (EventChannel, dumps, loads,
                         CloseEnoughJSONResponse, dummyRequest, render,
                         asResponse)
from .utils import (
    _assertRequestLogged, _assertTracebackLogged, FAILED_INPUT_VALIDATION)


class ArbitraryException(Exception):
    """
    An exception with distinct identity and no semantic value, useful at least
    to unit tests which verify proper error logging.
    """


class StructuredResultHandlingMixin(object):
    """
    A mixin defining tests for the L{structured} decorator's behavior with
    respect to the return value of the (or exception raised by) decorated
    function
    """
    def application(self, logger, result):
        """
        Subclasses should override this to return an object with a C{app}
        attribute that is a L{Klein} instance.  Tests will issue requests to
        this app and assert certain things about the response that is
        generated.
        """
        raise NotImplementedError("Subclass must provide an application")

    def render(self, resource, request):
        """
        Subclasses should override this to perform the Twisted Web resource
        rendering dance (mostly, call
        ``flocker.restapi.testtools.render()``).

        This hook is primarily to support the asynchronous cases where extra
        steps need to be taken after ``render()`` returns
        but before rendering is actually complete.

        @return: C{None}
        """

    @validateLogging(_assertRequestLogged(b"/foo/bar"))
    def test_encode(self, logger):
        """
        The return value of the decorated function is I{JSON} encoded and the
        result is written as the response body.
        """
        objects = {"foo": "bar", "baz": ["quux"]}
        request = dummyRequest(b"GET", b"/foo/bar", Headers(), b"")

        self.render(self.application(logger, objects).app.resource(), request)

        self.assertEqual(objects, loads(request._responseBody))

    @validateLogging(_assertTracebackLogged(TypeError))
    # This should be logged but stacking validateLogging decorators seems
    # to cause problems.
    # @validateLogging(_assertRequestLogged(b"/foo/exception"))
    def test_illegalResult(self, logger):
        """
        If the return value of the decorated function cannot be I{JSON} encoded
        then the response generated has the I{INTERNAL SERVER ERROR} code.
        """
        objects = {"foo": object()}
        request = dummyRequest(b"GET", b"/foo/bar", Headers(), b"")

        self.render(self.application(logger, objects).app.resource(), request)

        self.assertEqual(INTERNAL_SERVER_ERROR, request._code)

    @validateLogging(_assertRequestLogged(b"/foo/explicitresponse"))
    def test_explicitResponseObject(self, logger):
        """
        If the return value of the decorated function is an instance of
        L{EndpointResponse} then the response generated:

            - has the code given by the L{EndpointResponse} instance.
            - has a I{Content-Type} header set to I{application/json}.
            - has a JSON-encoded body indicating a successful response and
              giving the result from the L{EndpointResponse} instance.
        """
        application = self.application(logger, {})
        request = dummyRequest(
            b"GET", b"/foo/explicitresponse", Headers(), b"")
        self.render(application.app.resource(), request)

        expected = CloseEnoughJSONResponse(
            application.EXPLICIT_RESPONSE_CODE,
            Headers({b"content-type": [b"application/json"]}),
            application.EXPLICIT_RESPONSE_RESULT)
        return expected.verify(asResponse(request))

    @validateLogging(_assertRequestLogged(b"/foo/badrequest"))
    def test_badRequestRaised(self, logger):
        """
        If the decorated function raises L{BadRequest} then the generated
        response:

            - has the code taken from the exception.
            - has a I{Content-Type} header set to I{application/json}.
            - has a JSON-encoded body indicating an error response and giving
              details from the exception.
        """
        application = self.application(logger, {})
        request = dummyRequest(b"GET", b"/foo/badrequest", Headers(), b"")
        self.render(application.app.resource(), request)

        expected = CloseEnoughJSONResponse(
            application.BAD_REQUEST_CODE,
            Headers({b"content-type": [b"application/json"]}),
            application.BAD_REQUEST_RESULT)
        return expected.verify(asResponse(request))

    @validateLogging(_assertTracebackLogged(ArbitraryException))
    # See above
    # @validateLogging(_assertRequestLogged(b"/foo/exception"))
    def test_internalServerError(self, logger):
        """
        If the decorated function raises an exception, the HTTP response code
        is I{INTERNAL SERVER ERROR}.
        """
        request = dummyRequest(b"GET", b"/foo/exception", Headers(), b"")
        app = self.application(logger, None)
        self.render(app.app.resource(), request)
        self.assertEqual(INTERNAL_SERVER_ERROR, request._code)

    @validateLogging(None)
    def test_responseResultContainsIncident(self, logger):
        """
        If the decorated function raises an exception, the HTTP response body
        is a json-encoded object with a item set to an incident
        identifier.
        """
        request = dummyRequest(b"GET", b"/foo/exception", Headers(), b"")
        app = self.application(logger, None)
        self.render(app.app.resource(), request)
        logger.flushTracebacks(ArbitraryException)
        incident = loads(request._responseBody)
        action = LoggedAction.ofType(logger.messages, REQUEST)[0]
        # First message in action was action start with task_level /1, so
        # next task_level is /2:
        self.assertEqual(
            u"{}@/2".format(action.startMessage[u"task_uuid"]),
            incident)


class Execution(Names):
    """
    @cvar SYNCHRONOUS: The execution mode where application-level results are
        returned directly, synchronously from methods.

    @cvar SYNCHRONOUS_DEFERRED: The execution mode where application-level
        results are returned from methods as the result of a L{Deferred} which
        already has that result at the time of the return.

    @cvar ASYNCHRONOUS: The execution mode where application-level results are
        returned from methods as the result of a L{Deferred} but the
        L{Deferred} is only given the result some time after it is returned.
    """
    SYNCHRONOUS = NamedConstant()
    SYNCHRONOUS_DEFERRED = NamedConstant()
    ASYNCHRONOUS = NamedConstant()


class ResultHandlingApplication(object):
    """
    An application which implements the routes expected by the tests defined on
    L{StructuredResultHandlingMixin}.
    """
    app = Klein()

    BAD_REQUEST_CODE = PAYMENT_REQUIRED
    BAD_REQUEST_RESULT = u"additional details here"

    EXPLICIT_RESPONSE_CODE = GONE
    EXPLICIT_RESPONSE_RESULT = u"sorry that went missing I guess"

    def __init__(self, mode, logger, result):
        """
        @param mode: A constant from L{Execution} to determine how results will
            be returned from endpoints.
        """
        self.mode = mode
        self.logger = logger
        self.result = result
        self.kwargs = None
        self.ready = EventChannel()

    def _constructSuccess(self, result):
        """
        Turn C{result} into the kind of result appropriate to C{self.mode}.
        """
        if self.mode is Execution.SYNCHRONOUS:
            return result
        elif self.mode is Execution.SYNCHRONOUS_DEFERRED:
            return succeed(result)
        else:
            d = self.ready.subscribe()
            d.addCallback(lambda ignored: result)
            return d

    def _constructFailure(self, exception):
        """
        Turn C{exception} into the kind of exception appropriate to
        C{self.mode}.
        """
        if self.mode is Execution.SYNCHRONOUS:
            raise exception
        elif self.mode is Execution.SYNCHRONOUS_DEFERRED:
            return fail(Failure(exception))
        else:
            d = self.ready.subscribe()
            d.addCallback(lambda ignored: Failure(exception))
            return d

    @app.route(b"/foo/bar")
    @structured({}, {})
    def foo(self, **kwargs):
        self.kwargs = kwargs
        return self._constructSuccess(self.result)

    @app.route(b"/foo/exception")
    @structured({}, {})
    def bar(self):
        return self._constructFailure(ArbitraryException("Broken"))

    @app.route(b"/foo/validation")
    @structured({
        u'required': [u'abc'],
        u'properties': {u'int': {u'type': u'integer'}},
        }, {})
    def validation(self, **kwargs):
        self.kwargs = kwargs
        return self._constructSuccess(self.result)

    @app.route(b"/foo/badrequest")
    @structured({}, {})
    def badrequest(self):
        return self._constructFailure(
            BadRequest(self.BAD_REQUEST_CODE, self.BAD_REQUEST_RESULT))

    @app.route(b"/foo/explicitresponse")
    @structured({}, {})
    def explicitresponse(self):
        return self._constructSuccess(EndpointResponse(
            self.EXPLICIT_RESPONSE_CODE, self.EXPLICIT_RESPONSE_RESULT))

    @app.route(b"/baz/<routingValue>")
    @structured({}, {})
    def baz(self, **kwargs):
        self.kwargs = kwargs
        return self._constructSuccess(self.result)

    @app.route(b"/foo/badresponse")
    @structured({}, {'type': 'string'})
    def badResponse(self, **kwargs):
        self.kwargs = kwargs
        return self._constructSuccess({})


class SynchronousStructuredResultHandlingTests(StructuredResultHandlingMixin,
                                               SynchronousTestCase):
    """
    Apply the tests defined by L{StructuredResultHandlingMixin} to an
    application which returns results synchronously without involving
    L{Deferred}.
    """
    def render(self, resource, request):
        render(resource, request)

    def application(self, logger, result):
        return ResultHandlingApplication(Execution.SYNCHRONOUS, logger, result)


class SynchronousDeferredStructuredResultHandlingTests(
        StructuredResultHandlingMixin, SynchronousTestCase):
    """
    Apply the tests defined by L{StructuredResultHandlingMixin} to an
    application which returns results synchronously as the result of an
    already-fired L{Deferred}.
    """
    def render(self, resource, request):
        render(resource, request)

    def application(self, logger, result):
        return ResultHandlingApplication(
            Execution.SYNCHRONOUS_DEFERRED, logger, result)


class AsynchronousStructuredResultHandlingTests(StructuredResultHandlingMixin,
                                                SynchronousTestCase):
    """
    Apply the tests defined by L{StructuredResultHandlingMixin} to an
    application which returns results asynchronously as the future result of a
    not-yet-fired L{Deferred}.
    """
    def render(self, resource, request):
        """
        Render the resource in the usual way and afterwards poke the
        application object to actually deliver its result.
        """
        render(resource, request)
        self.ready.callback(None)

    def application(self, logger, result):
        app = ResultHandlingApplication(
            Execution.ASYNCHRONOUS, logger, result)
        self.ready = app.ready
        return app


class StructuredJSONTests(SynchronousTestCase):
    """
    Tests for the L{structured} behavior related to decoding JSON requests and
    serializing JSON responses.
    """
    def Application(self, logger, result):
        return ResultHandlingApplication(Execution.SYNCHRONOUS, logger, result)

    def test_name(self):
        """
        The name of the wrapper function function returned by the decorator has
        the same name as the decorated function.
        """
        application = self.Application(None, None)
        self.assertEqual("foo", application.foo.__name__)

    @validateLogging(_assertRequestLogged(b"/foo/bar"))
    def test_decode(self, logger):
        """
        The I{JSON}-encoded request body is decoded into Python objects and
        passed as keyword arguments to the decorated function.
        """
        objects = {"foo": "bar", "baz": ["quux"]}
        request = dummyRequest(
            b"PUT", b"/foo/bar",
            Headers({b"content-type": [b"application/json"]}), dumps(objects))

        app = self.Application(logger, None)
        render(app.app.resource(), request)
        self.assertEqual(objects, app.kwargs)

    def assertNoDecodeLogged(self, logger, method):
        """
        The I{JSON}-encoded request body is ignored when the given method is
        used.

        @param method: A HTTP method.
        @type method: L{bytes}
        """
        objects = {"foo": "bar", "baz": ["quux"]}
        request = dummyRequest(
            method, b"/foo/bar",
            Headers({b"content-type": [b"application/json"]}), dumps(objects))

        app = self.Application(logger, None)
        render(app.app.resource(), request)
        self.assertEqual({}, app.kwargs)

    @validateLogging(_assertRequestLogged(b"/foo/bar"))
    def test_noDecodeGET(self, logger):
        """
        The I{JSON}-encoded request body is ignored when the I{GET} method is
        used.
        """
        self.assertNoDecodeLogged(logger, b"GET")

    @validateLogging(_assertRequestLogged(b"/foo/bar"))
    def test_noDecodeDELETE(self, logger):
        """
        The I{JSON}-encoded request body is ignored when the I{DELETE} method
        is used.
        """
        self.assertNoDecodeLogged(logger, b"DELETE")

    @validateLogging(_assertRequestLogged(b"/foo/bar"))
    def test_malformedRequest(self, logger):
        """
        If the request body cannot be decoded as a I{JSON} blob then the
        request automatically receives a I{BAD REQUEST} response.
        """
        app = self.Application(logger, None)
        request = dummyRequest(
            b"PUT", b"/foo/bar",
            Headers({b"content-type": [b"application/json"]}), b"foo bar")
        render(app.app.resource(), request)

        # The endpoint should not have been called.
        self.assertIs(None, app.kwargs)

        expected = CloseEnoughJSONResponse(
            BAD_REQUEST,
            Headers({b"content-type": [b"application/json"]}),
            {u"description": DECODING_ERROR_DESCRIPTION})
        return expected.verify(asResponse(request))

    @validateLogging(_assertRequestLogged(b"/foo/validation"))
    def test_validationError(self, logger):
        """
        If the request body doesn't match the provided schema, then the
        request automatically receives a I{BAD REQUEST} response.
        """
        request = dummyRequest(
            b"PUT", b"/foo/validation",
            Headers({b"content-type": [b"application/json"]}),
            dumps({u'int': []}))

        app = self.Application(logger, None)
        render(app.app.resource(), request)

        response = loads(request._responseBody)

        self.assertEqual(
            (request._code, response[u'description'],
             len(response[u'errors'])),
            (BAD_REQUEST, FAILED_INPUT_VALIDATION, 2))

    @validateLogging(_assertTracebackLogged(ValidationError))
    # See above
    # @validateLogging(_assertRequestLogged(b"/foo/badresponse"))
    def test_responseValidationError(self, logger):
        """
        If the response body doesn't match the provided schema, then the
        request automatically receives a I{INTERNAL SERVER ERROR} response.
        """
        request = dummyRequest(
            b"GET", b"/foo/badresponse",
            Headers({b"content-type": [b"application/json"]}), b"")

        app = self.Application(logger, None)
        render(app.app.resource(), request)

        self.assertEqual(request._code, INTERNAL_SERVER_ERROR)

    @validateLogging(_assertRequestLogged(b"/foo/bar"))
    def test_wrongContentTypeRequest(self, logger):
        """
        If the request does not use the I{GET} method and does not include a
        I{Content-Type: application/json} header then it automatically receives
        a I{BAD REQUEST} response.
        """
        app = self.Application(logger, None)
        request = dummyRequest(b"PUT", b"/foo/bar", Headers(), dumps({}))
        render(app.app.resource(), request)

        # The endpoint should not have been called.
        self.assertIs(None, app.kwargs)

        expected = CloseEnoughJSONResponse(
            BAD_REQUEST,
            Headers({b"content-type": [b"application/json"]}),
            {u"description": ILLEGAL_CONTENT_TYPE_DESCRIPTION})
        return expected.verify(asResponse(request))

    @validateLogging(_assertRequestLogged(b"/baz/quux"))
    def test_onlyArgumentsFromRoute(self, logger):
        """
        If an endpoint's route defines additional arguments for the endpoint
        those arguments are also passed by keyword to the decorated function.
        """
        request = dummyRequest(
            b"POST", b"/baz/quux",
            Headers({b"content-type": [b"application/json"]}),
            dumps({}))
        app = self.Application(logger, {})
        render(app.app.resource(), request)
        self.assertEqual({"routingValue": "quux"}, app.kwargs)

    @validateLogging(_assertRequestLogged(b"/baz/quux"))
    def test_mixedArgumentsFromRoute(self, logger):
        """
        If an endpoint's route defines additional arguments for the endpoint
        those arguments are also passed by keyword to the decorated function
        along with arguments from the JSON body of the request.
        """
        request = dummyRequest(
            b"POST", b"/baz/quux",
            Headers({b"content-type": [b"application/json"]}),
            dumps({"jsonValue": True}))
        app = self.Application(logger, {})
        render(app.app.resource(), request)
        self.assertEqual(
            {"jsonValue": True, "routingValue": "quux"}, app.kwargs)


class UserDocumentationTests(SynchronousTestCase):
    """
    Tests for L{user_documentation}.
    """

    def test_decoration(self):
        """
        Decorating a function with L{user_documentation} sets the
        C{user_documentation} attribtue of the function to the passed
        argument.
        """
        @user_documentation("Some text")
        def f():
            pass
        self.assertEqual(f.userDocumentation, "Some text")


class NotAllowedTests(SynchronousTestCase):
    """
    Tests for the HTTP method restriction functionality imposed by the routing
    decorator.
    """
    class Application(object):
        app = Klein()

        @app.route(b"/foo/bar", methods={b"GET"})
        @structured({}, {})
        def gettable(self):
            return b"OK"

    def test_notAllowed(self):
        """
        If an endpoint is restricted to being used with certain HTTP methods
        then a request for that endpoint using a different method receives a
        I{NOT ALLOWED} response.
        """
        app = self.Application()
        request = dummyRequest(b"POST", b"/foo/bar", Headers(), dumps({}))
        render(app.app.resource(), request)
        self.assertEqual(NOT_ALLOWED, request._code)


class NotFoundTests(SynchronousTestCase):
    """
    Tests for the response behavior relating to requests for non-existent
    resources.
    """
    class Application(object):
        app = Klein()

        @app.route(b"/foo/bar")
        @structured({}, {})
        def exists(self):
            return b"OK"

    def test_notFound(self):
        """
        If an endpoint is restricted to being used with certain HTTP methods
        then a request for that endpoint using a different method receives a
        I{NOT ALLOWED} response.
        """
        app = self.Application()
        request = dummyRequest(b"GET", b"/quux", Headers(), b"")
        render(app.app.resource(), request)
        self.assertEqual(NOT_FOUND, request._code)
