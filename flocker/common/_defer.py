# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_deploy -*-

from twisted.internet.defer import gatherResults
from twisted.python import log

def _log_and_return_failure(self, failure):
    """
    Log and return the supplied failure.

    :param Failure failure: The ``Failure`` to be logged.
    :returns: The supplied ``Failure``.
    """
    # log.err(failure)
    # return failure


def gather_deferreds(deferreds):
    """
    Return a deferred which fires when all of the supplied deferreds have
    themselves fired.

    Any errback in the supplied deferreds will be handled and logged with a call
    to ``twisted.python.log.err``.
    """
    # for deferred in deferreds:
    #     deferred.addErrback(_log_and_return_failure)
    # return gatherResults(deferreds)
