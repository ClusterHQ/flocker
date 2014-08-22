# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_deploy -*-

"""
Various helpers for dealing with Deferred APIs in flocker.
"""

from twisted.internet.defer import gatherResults
from twisted.python import log


def gather_deferreds(deferreds):
    """
    Return a ``Deferred`` which fires when all of the supplied
    ``deferreds`` have themselves fired.

    Any errback in the supplied ``deferreds`` will be handled and logged
    with a call to ``twisted.python.log.err``.

    See ``twisted.internet.defer.gatherResults`` which this function wraps.

    :param list deferreds: A ``list`` of ``Deferred``\ s whose results will
        be gathered.
    :returns: A ``Deferred`` which calls back with a ``list`` of all the
        results of the supplied ``deferreds`` when all the supplied
        ``deferreds`` have succeeded or which will errback with a
        ``FirstError`` failure as soon as one of the supplied ``deferreds`
        fails.
    """
    # Gather once to get the results OR the first failure
    first_failure = gatherResults(deferreds)

    for deferred in deferreds:
        deferred.addErrback(lambda failure: log.err(failure))
    # After adding logging callbacks, gather again so as to wait for all
    # the supplied deferreds to fire.
    gathering = gatherResults(deferreds)

    # Then return the result of the first gather.
    gathering.addCallback(lambda ignored: first_failure)
    return gathering

