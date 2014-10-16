# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
This module defines the presentation of error conditions that can be
encountered by the implementation of the API.
"""

__all__ = [
    "BadRequest", "InvalidRequestJSON", "makeBadRequest",

    "DECODING_ERROR_DESCRIPTION", "ILLEGAL_CONTENT_TYPE_DESCRIPTION",

    "DECODING_ERROR", "ILLEGAL_CONTENT_TYPE", "UNAUTHORIZED",
    "ENTITY_NOT_FOUND",

    "NameCollision",

    "UNPROCESSABLE_REQUEST",
    ]

from inspect import cleandoc

from twisted.web.http import BAD_REQUEST, FORBIDDEN, NOT_FOUND

# HTTP response code indicating the request is syntactically correct but
# semantically wrong, as defined in
# <https://tools.ietf.org/html/rfc4918#section-11.2> (which calls it
# "Unprocessable Entity" which involves them defining "Entity" as the
# request body for some bizarre reason). This should be used when the
# request passed JSON validation, but is telling us to do something that
# doesn't make sense and is not covered by other HTTP response codes.
# BAD_REQUEST (400) should be used for syntactically incorrect requests.
UNPROCESSABLE_REQUEST = 422


class BadRequest(Exception):
    """
    An endpoint can raise a L{BadRequest} (or subclass) instance to return an
    error response to the client without triggering incident logging.

    Use this for input validation failures, for example.
    """
    def __init__(self, code, result):
        """
        @param code: The HTTP response code to set in the response.
        @type code: L{int}

        @param result: The value to put into the C{u"result"} field of the
            response body.
        """
        self.code = code
        self.result = result


def makeBadRequest(code=BAD_REQUEST, **result):
    """
    Create a new L{BadRequest} instance with the given result.
    """
    return BadRequest(code, result)


DECODING_ERROR_DESCRIPTION = cleandoc(u"""
    The request body could not be decoded according to the value of the
    Content-Type header.
    """)
ILLEGAL_CONTENT_TYPE_DESCRIPTION = cleandoc(u"""
    The request Content-Type was not a supported type (application/json).
    """)
NOT_FOUND_DESCRIPTION = cleandoc(u"""
    The specified entity either does not exist or you are not allowed to access
    it.
    """)
UNAUTHORIZED_DESCRIPTION = cleandoc("""
    The user is not authorized to do this operation.
    """)

DECODING_ERROR = makeBadRequest(description=DECODING_ERROR_DESCRIPTION)
ILLEGAL_CONTENT_TYPE = makeBadRequest(
    description=ILLEGAL_CONTENT_TYPE_DESCRIPTION)
ENTITY_NOT_FOUND = makeBadRequest(
    code=NOT_FOUND, description=NOT_FOUND_DESCRIPTION)
UNAUTHORIZED = makeBadRequest(
    FORBIDDEN, description=UNAUTHORIZED_DESCRIPTION)


class InvalidRequestJSON(BadRequest):
    description = cleandoc(u"""
    The provided JSON doesn't match the required schema.
    """)

    __doc__ = description

    def __init__(self, errors, schema):
        # Schema is currently ignored because references need to be
        # resolved before it would be useful to a user.
        BadRequest.__init__(
            self,
            BAD_REQUEST,
            {u"description": self.description, u"errors": errors})


class NameCollision(Exception):
    """
    An entity was created with a name that already exists.
    """
