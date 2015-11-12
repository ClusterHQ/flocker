# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Driver tests for the control service benchmarks.
"""

from itertools import count, repeat

from zope.interface import implementer

from twisted.internet.defer import Deferred, succeed, fail
from twisted.trial.unittest import TestCase

from benchmark._driver import benchmark
from benchmark._operations import IProbe, IOperation


class FakeMeasurement:

    def __init__(self, measurements):
        """
        :param measurements: An iterator providing measurement to be
            returned on each call.
        """
        self.measurements = measurements

    def __call__(self, f, *a, **kw):
        def finished(ignored):
            return next(self.measurements)

        d = f(*a, **kw)
        d.addCallback(finished)
        return d


@implementer(IProbe)
class FakeProbe:
    """
    A probe performs a single operation, which can be timed.
    """
    def __init__(self, good):
        self.good = good

    def run(self):
        if self.good:
            return succeed(None)
        else:
            return fail(RuntimeError('ProbeFailed'))

    def cleanup(self):
        return succeed(None)


@implementer(IOperation)
class FakeOperation:

    def __init__(self, succeeds):
        """
        :param succeeds: An iterator providing a boolean indicating
            whether the probe will succeed.
        """
        self.succeeds = succeeds

    def get_probe(self):
        return FakeProbe(next(self.succeeds))


class FakeScenario:

    class FakeRunningScenario:

        def __init__(self):
            self.scenario_established = succeed(None)
            self.scenario_maintained = Deferred()

        def established(self):
            return self.scenario_established

        def maintained(self):
            return self.scenario_maintained

        def stop(self):
            return succeed(None)

    def start(self):
        return self.FakeRunningScenario()


class FakeCollapsingScenario:

    class FakeRunningScenario:

        def __init__(self):
            self.scenario_established = succeed(None)
            self.scenario_maintained = Deferred()

        def established(self):
            return self.scenario_established

        def maintained(self):
            return fail(RuntimeError('collapse'))

        def stop(self):
            return succeed(None)

    def start(self):
        return self.FakeRunningScenario()


class SampleTest(TestCase):

    def test_good_probes(self):
        """
        Sampling returns results when probes succeed.
        """
        samples_ready = benchmark(
            FakeMeasurement(count(5)),
            FakeOperation(repeat(True)),
            FakeScenario(),
            3)

        def check(samples):
            self.assertEqual(
                samples, [{'success': True, 'value': x} for x in [5, 6, 7]])
        samples_ready.addCallback(check)
        return samples_ready

    def test_bad_probes(self):
        """
        Sampling returns reasons when probes fail.
        """
        samples_ready = benchmark(
            FakeMeasurement(count(5)),
            FakeOperation(repeat(False)),
            FakeScenario(),
            3)

        def check(samples):
            # We don't care about the actual value for reason.
            for s in samples:
                if 'reason' in s:
                    s['reason'] = None
            self.assertEqual(
                samples,
                [{'success': False, 'reason': None} for x in [5, 6, 7]])
        samples_ready.addCallback(check)
        return samples_ready

    def test_scenario_collapse(self):
        """
        If the scenario collapses, a failure is returned.
        """
        samples_ready = benchmark(
            FakeMeasurement(count(5)),
            FakeOperation(repeat(True)),
            FakeCollapsingScenario(),
            3)
        self.assertFailure(samples_ready, RuntimeError)
