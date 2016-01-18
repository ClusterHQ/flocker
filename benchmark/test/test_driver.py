# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
Driver tests for the control service benchmarks.
"""

from itertools import count, repeat

from zope.interface import implementer

from eliot.testing import capture_logging

from twisted.internet.defer import Deferred, succeed, fail

from benchmark._driver import benchmark, sample
from benchmark._interfaces import IScenario, IProbe, IOperation, IMetric

from flocker.testtools import AsyncTestCase, TestCase


@implementer(IMetric)
class FakeMetric(object):

    def __init__(self, measurements):
        """
        :param measurements: An iterator providing measurement to be
            returned on each call.
        """
        self.measurements = measurements

    def measure(self, f, *a, **kw):
        def finished(ignored):
            return next(self.measurements)

        d = f(*a, **kw)
        d.addCallback(finished)
        return d


@implementer(IProbe)
class FakeProbe(object):
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
class FakeOperation(object):

    def __init__(self, succeeds):
        """
        :param succeeds: An iterator providing a boolean indicating
            whether the probe will succeed.
        """
        self.succeeds = succeeds

    def get_probe(self):
        return FakeProbe(next(self.succeeds))


@implementer(IOperation)
class BrokenGetProbeOperation(object):

    def get_probe(self):
        return fail(RuntimeError('get_probe failed'))


@implementer(IScenario)
class FakeScenario(object):

    def __init__(self, maintained=Deferred()):
        self._maintained = maintained

    def start(self):
        return succeed(None)

    def maintained(self):
        return self._maintained

    def stop(self):
        return succeed(None)


class SampleTest(TestCase):
    """
    Test sample function.
    """

    @capture_logging(None)
    def test_good_probe(self, logger):
        """
        Sampling returns value when probe succeeds.
        """
        sampled = sample(FakeOperation(repeat(True)), FakeMetric(repeat(5)), 1)

        self.assertEqual(
            self.successResultOf(sampled), {'success': True, 'value': 5})

    @capture_logging(None)
    def test_bad_probe(self, logger):
        """
        Sampling returns reason when probe fails.
        """
        sampled = sample(
            FakeOperation(repeat(False)), FakeMetric(repeat(5)), 1)

        def filter(sample):
            if 'reason' in sample:
                sample['reason'] = type(sample['reason'])
            return sample
        sampled.addCallback(filter)

        self.assertEqual(
            self.successResultOf(sampled), {'success': False, 'reason': str}
        )

    @capture_logging(None)
    def test_failed_get_probe(self, logger):
        """
        Sampling returns reason when get_probe fails.
        """
        sampled = sample(
            BrokenGetProbeOperation(), FakeMetric(repeat(5)), 1)

        result = self.successResultOf(sampled)

        self.assertFalse(result['success'])
        self.assertIn('get_probe failed', result['reason'])


class BenchmarkTest(AsyncTestCase):
    """
    Test benchmark function.
    """
    # Test using `AsyncTestCase` rather than `TestCase` because the
    # `benchmark` function uses `twisted.task.cooperate`, which uses the
    # global reactor.
    #
    # This could be fixed by making the cooperator to use a parameter and
    # supplying one driven by a fake IReactorTime (eg Clock).

    @capture_logging(None)
    def test_good_probes(self, logger):
        """
        Sampling returns results when probes succeed.
        """
        samples_ready = benchmark(
            FakeScenario(),
            FakeOperation(repeat(True)),
            FakeMetric(count(5)),
            3)

        def check(outputs):
            self.assertEqual(
                outputs,
                ([{'success': True, 'value': x} for x in [5, 6, 7]], None))
        samples_ready.addCallback(check)
        return samples_ready

    @capture_logging(None)
    def test_bad_probes(self, logger):
        """
        Sampling returns reasons when probes fail.
        """
        samples_ready = benchmark(
            FakeScenario(),
            FakeOperation(repeat(False)),
            FakeMetric(count(5)),
            3)

        def check(outputs):
            # We don't care about the actual value for reason.
            for s in outputs[0]:
                if 'reason' in s:
                    s['reason'] = None
            self.assertEqual(
                outputs,
                (
                    [{'success': False, 'reason': None} for x in [5, 6, 7]],
                    None)
                )
        samples_ready.addCallback(check)
        return samples_ready

    def test_scenario_collapse(self):
        """
        If the scenario collapses, a failure is returned.
        """
        samples_ready = benchmark(
            FakeScenario(fail(RuntimeError('collapse'))),
            FakeOperation(repeat(True)),
            FakeMetric(count(5)),
            3)
        self.assertFailure(samples_ready, RuntimeError)

    @capture_logging(None)
    def test_sample_count(self, _logger):
        """
        The sample count determines the number of samples.
        """
        samples_ready = benchmark(
            FakeScenario(),
            FakeOperation(repeat(True)),
            FakeMetric(count(5)),
            5)

        def check(outputs):
            samples, scenario_metrics = outputs
            self.assertEqual(len(samples), 5)
        samples_ready.addCallback(check)
        return samples_ready
