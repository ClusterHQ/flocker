# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
Utilities for testing REST APIs.
"""

from klein import Klein
from klein.resource import KleinResource

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


FAILED_INPUT_VALIDATION = (
    u"The provided JSON doesn't match the required schema.")


def _assertRequestLogged(path, method=b"GET"):
    def actuallyAssert(self, logger):
        request = LoggedAction.ofType(logger.messages, REQUEST)[0]
        assertContainsFields(self, request.startMessage, {
            u"request_path": path.decode("ascii"),
            u"method": method,
        })
        return request
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


class _anything(object):
    """
    An instance of this class compares equal to any other object.
    """
    def __eq__(self, other):
        return True

    def __ne__(self, other):
        return False

anything = _anything()
