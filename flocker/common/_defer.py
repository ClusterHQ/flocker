# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_deploy -*-

"""
Various helpers for dealing with Deferred APIs in flocker.
"""

from twisted.internet.defer import gatherResults
from twisted.python import log


class GatherDeferredsAPI(object):
    """
    An API for gather_deferreds which logs errors in all its supplied
    deferreds, but which allows logging to be disabled for certain unit tests.

    :ivar log_errors: See ``__init__``.
    """
    def __init__(self, log_errors=True):
        """
        :param bool log_errors: A flag which controls whether error logging is
            enabled. Allows logging behaviour to be overridden in
            tests. Default is ``True``.
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
        Return a ``Deferred`` which fires when all of the supplied
        ``Deferred``\ s have themselves fired.

        Any errback in the supplied ``Deferred``\ s will be handled and logged
        with a call to ``twisted.python.log.err``.

        :param list deferreds: A ``list`` of ``Deferred``\ s whose results will
            be gathered.
        :returns: A ``Deferred`` which calls back when all the supplied
            ``deferreds`` have succeeded or which will errback when at least
            one has failed.
        """
        if self.log_errors:
            for deferred in deferreds:
                deferred.addErrback(self._log_and_return_failure)
        return gatherResults(deferreds, consumeErrors=True)


gather_deferreds = GatherDeferredsAPI().gather_deferreds
