# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
This module implements tools for exposing Python methods as API endpoints.
"""

from __future__ import absolute_import

__all__ = [
    "EndpointResponse", "structured", "user_documentation",
    ]

from functools import wraps

from json import loads, dumps

from pyrsistent import PRecord, field, pvector

from twisted.internet.defer import maybeDeferred
from twisted.web.http import OK, INTERNAL_SERVER_ERROR

from eliot import Logger, writeFailure
from eliot.twisted import DeferredContext

from ._error import (
    ILLEGAL_CONTENT_TYPE, DECODING_ERROR, BadRequest, InvalidRequestJSON)
from ._logging import LOG_SYSTEM, REQUEST, JSON_REQUEST
from ._schema import getValidator

_ASCENDING = b"ascending"
_DESCENDING = b"descending"

_logger = Logger()


class EndpointResponse(object):
    """
    An endpoint can return an L{EndpointResponse} instance to return a custom
    response code to the client along with a successful response body.
    """
    def __init__(self, code, result):
        """
        @param code: The HTTP response code to set in the response.
        @type code: L{int}

        @param result: The (structured) value to put into the response
            body.  This must be JSON encodeable.
        """
        self.code = code
        self.result = result


def _get_logger(self):
    """
    Find the specific or default ``Logger``.

    :return: A ``Logger`` object.
    """
    try:
        logger = self.logger
    except AttributeError:
        return _logger
    else:
        if logger is None:
            logger = _logger
        return logger


def _logging(original):
    """
    Decorate a method which implements an API endpoint to add Eliot-based
    logging.

    Calls to the decorated function will be in a L{REQUEST} action.  If the
    decorated function raises an exception then the exception will be logged
    and a token which identifies that log event sent in the response.
    """
    @wraps(original)
    def logger(self, request, **routeArguments):
        logger = _get_logger(self)

        # If this is ever more than ASCII we might have issues? or maybe
        # this is pre-url decoding?
        # https://clusterhq.atlassian.net/browse/FLOC-1602
        action = REQUEST(logger, request_path=request.path,
                         method=request.method)

        # Generate a serialized action context that uniquely identifies
        # position within the logs, though there won't actually be any log
        # message with that particular task level:
        incidentIdentifier = action.serialize_task_id()

        with action.context():
            d = DeferredContext(original(self, request, **routeArguments))

        def failure(reason):
            if reason.check(BadRequest):
                code = reason.value.code
                result = reason.value.result
            else:
                writeFailure(reason, logger, LOG_SYSTEM)
                code = INTERNAL_SERVER_ERROR
                result = incidentIdentifier
            request.setResponseCode(code)
            request.responseHeaders.setRawHeaders(
                b"content-type", [b"application/json"])
            return dumps(result)
        d.addErrback(failure)
        d.addActionFinish()
        return d.result

    return logger


def _serialize(outputValidator):
    """
    Decorate a function so that its return value is automatically JSON encoded
    into a structure indicating a successful result.

    @param outputValidator: A L{jsonschema} validator for the returned JSON.

    @return: A decorator that decorates a function with the signature
        of a Klein route endpoint that may return a Deferred.
    """
    def deco(original):
        def success(result, request):
            code = OK
            if isinstance(result, EndpointResponse):
                code = result.code
                result = result.result
            outputValidator.validate(result)
            request.responseHeaders.setRawHeaders(
                b"content-type", [b"application/json"])
            request.setResponseCode(code)
            return dumps(result)

        def doit(self, request, **routeArguments):
            result = maybeDeferred(original, self, request, **routeArguments)
            result.addCallback(success, request)
            return result

        return doit
    return deco


def structured(inputSchema, outputSchema, schema_store=None):
    """
    Decorate a Klein-style endpoint method so that the request body is
    automatically decoded and the response body is automatically encoded.

    Items in the object encoded in the request body will be passed to
    C{original} as keyword arguments.  For example::

        {"foo": "bar"}

    If this request body is received it will be as if the decorated function
    were called like::

        original(foo="bar")

    The encoded form of the object returned by C{original} will define the
    response body.

    :param inputSchema: JSON Schema describing the request body.
    :param outputSchema: JSON Schema describing the response body.
    :param schema_store: A mapping between schema paths
        (e.g. ``b/v1/types.json``) and the JSON schema structure, allowing
        input/output schemas to just be references.
    """
    if schema_store is None:
        schema_store = {}
    inputValidator = getValidator(inputSchema, schema_store)
    outputValidator = getValidator(outputSchema, schema_store)

    def deco(original):
        @wraps(original)
        @_logging
        @_serialize(outputValidator)
        def loadAndDispatch(self, request, **routeArguments):
            if request.method in (b"GET", b"DELETE"):
                objects = {}
            else:
                contentType = request.requestHeaders.getRawHeaders(
                    b"content-type", [None])[0]
                if contentType != b"application/json":
                    raise ILLEGAL_CONTENT_TYPE

                body = request.content.read()
                try:
                    objects = loads(body)
                except ValueError:
                    raise DECODING_ERROR

                errors = []
                for error in inputValidator.iter_errors(objects):
                    errors.append(error.message)
                if errors:
                    raise InvalidRequestJSON(errors=errors, schema=inputSchema)

            eliot_action = JSON_REQUEST(_get_logger(self), json=objects.copy())
            with eliot_action.context():
                # Just assume there are no conflicts between these collections
                # of arguments right now.  When there is a schema for the JSON
                # hopefully we can do some static verification that no routing
                # arguments conflict with any top-level keys in the request
                # body and then we can be sure there are no conflicts here.
                objects.update(routeArguments)

                d = DeferredContext(maybeDeferred(original, self, **objects))

                def got_result(result):
                    code = OK
                    json = result
                    if isinstance(result, EndpointResponse):
                        code = result.code
                        json = result.result
                    eliot_action.add_success_fields(code=code, json=json)
                    return result
                d.addCallback(got_result)
                d.addActionFinish()
                return d.result

        loadAndDispatch.inputSchema = inputSchema
        loadAndDispatch.outputSchema = outputSchema
        return loadAndDispatch
    return deco


class UserDocumentation(PRecord):
    """
    """
    text = field(type=unicode, mandatory=True)
    header = field(type=unicode, mandatory=True)
    section = field(type=unicode, mandatory=True)
    examples = field(mandatory=True)


def user_documentation(text, header, section, examples=None):
    """
    Annotate a klein-style endpoint to include user-facing documentation.

    :param unicode text: The documentation to be included in the generated API
        documentation along with the decorated endpoint.

    :param unicode header: The header to be included in the generated API docs.

    :param unicode section: The section of the docs to include this route in.

    :param list examples: The identifiers of any examples demonstrating the use
        of this example to include in the generated API documentation along
        with the decorated endpoint.
    """
    if examples is None:
        examples = []

    def deco(f):
        f.user_documentation = UserDocumentation(
            text=text, examples=pvector(examples),
            header=header, section=section)
        return f
    return deco


def private_api(f):
    """
    Annotate a klein-style endpoint to indicate it should not be included
    in user-facing API documentation.
    """
    f.private_api = True
    return f
