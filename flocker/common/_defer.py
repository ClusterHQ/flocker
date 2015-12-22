# Copyright ClusterHQ Inc.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_deploy -*-

"""
Various helpers for dealing with Deferred APIs in flocker.
"""

from twisted.internet.defer import gatherResults

from eliot import write_failure


def gather_deferreds(deferreds):
    """
    Return a ``Deferred`` which fires when all of the supplied
    ``deferreds`` have themselves fired.

    Any errback in the supplied ``deferreds`` will be handled and logged
    with a call to ``twisted.python.log.err``.

    See ``twisted.internet.defer.gatherResults`` which this function wraps.

    :param list deferreds: A ``list`` of ``Deferred``\ s whose results will
        be gathered.
    :returns: A ``Deferred`` which fires only when all the supplied
        ``deferreds`` have fired. If all the supplied ``deferreds`` succeed the
        result will callback with a ``list`` of all the results.  If any of the
        supplied ``deferreds`` fail, the result will errback with a
        ``FirstError`` failure containing a reference to the failure produced
        by the first of the ``deferreds`` to fail.
    """
    # Gather once to get the results OR the first failure
    results_or_first_failure = gatherResults(deferreds)

    def log_and_discard(failure):
        """
        Log the supplied failure and discard it.

        The failure is deliberately discarded so as to prevent any further
        logging of this failure when the deferred is eventually garbage
        collected.

        :param Failure failure: The ``Failure`` to be logged.
        """
        write_failure(failure)

    for deferred in deferreds:
        deferred.addErrback(log_and_discard)

    # After adding logging callbacks, gather again so as to wait for all
    # the supplied deferreds to fire.
    gathering = gatherResults(deferreds)

    # Then return the result of the first gather.
    gathering.addCallback(lambda ignored: results_or_first_failure)
    return gathering
