# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
No load scenario for the control service benchmarks.
"""

from zope.interface import implementer

from twisted.internet.defer import Deferred, succeed

from .._interfaces import IScenario


@implementer(IScenario)
class NoLoadScenario(object):
    """
    A scenario that places no additional load on the cluster.
    """

    def __init__(self, clock, cluster):
        self._maintained = Deferred()

    def start(self):
        """
        :return: A Deferred that fires when the desired scenario is
            established (e.g. that a certain load is being applied).
        """
        return succeed(self)  # no setup needed

    def maintained(self):
        """
        :return: A Deferred that fires with an errback if the desired
            scenario fails to hold between being established and being
            stopped.  This Deferred never fires with a callback.
        """
        return self._maintained

    def stop(self):
        """
        Stop the scenario from being maintained.

        :return Deferred[None]: No scenario metrics.
        """
        return succeed(None)
