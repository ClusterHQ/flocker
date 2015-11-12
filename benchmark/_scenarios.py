# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Scenarios for the control service benchmarks.
"""

from twisted.internet.defer import maybeDeferred, Deferred, succeed


class RunningScenario:

    def __init__(self):
        self.scenario_established = Deferred()
        self.scenario_maintained = Deferred()

    def established(self):
        """
        :return: A Deferred that fires when the desired scenario is
            established (e.g. that a certain load is being applied).
        """
        return self.scenario_established

    def maintained(self):
        """
        :return: A Deferred that fires with an errback id the desired
            scenario fails to hold between being established and being
            stopped.  This Deferred never fires with a callback.
        """
        return self.scenario_maintained

    def stop(self):
        """
        Stop the scenario from being maintained.

        :return: A Deferred that fires when the desired scenario is
            stopped.
        """
        return succeed(None)


class _NoLoadScenario(object):

    def __init__(self, clock, client):
        self.clock = clock
        self.client = client

    def start(self):
        running = RunningScenario()
        running.established().callback(None)  # no setup needed
        return running

_scenarios = {
    'no-load': _NoLoadScenario,
}

supported_scenarios = _scenarios.keys()
default_scenario = 'no-load'


def get_scenario(clock, client, name):
    return maybeDeferred(_scenarios[name], clock=clock, client=client)
