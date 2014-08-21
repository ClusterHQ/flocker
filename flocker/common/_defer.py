# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_deploy -*-

from twisted.internet.defer import gatherResults
from twisted.python import log

class GatherDeferredsAPI(object):
    """
    An API for gather_deferreds which allows logging to be disabled for certain
    unit tests.
    """
    def __init__(self, log_errors=True):
        """
        :param bool log_errors: A flag which controls whether error logging is
            enabled.
        """
        self.log_errors = log_errors

    def _log_and_return_failure(self, failure):
        """
        Log and return the supplied failure.

        :param Failure failure: The ``Failure`` to be logged.
        :returns: The supplied ``Failure``.
        """
        log.err(failure)
        return failure

    def gather_deferreds(self, deferreds):
        """
        Return a deferred which fires when all of the supplied deferreds have
        themselves fired.

        Any errback in the supplied deferreds will be handled and logged with a call
        to ``twisted.python.log.err``.
        """
        if self.log_errors:
            for deferred in deferreds:
                deferred.addErrback(self._log_and_return_failure)
        return gatherResults(deferreds, consumeErrors=True)


gather_deferreds = GatherDeferredsAPI().gather_deferreds
