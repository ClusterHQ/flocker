# Copyright 2016 ClusterHQ Inc.  See LICENSE file for details.

from zope.interface import implementer

from twisted.internet.defer import succeed
from twisted.internet.task import Clock

from flocker.testtools import TestCase

from benchmark._interfaces import IRequest
from benchmark.scenarios._request_load import RequestLoadScenario


@implementer(IRequest)
class TestRequest:
    """
    A very simple request that does nothing but always succeeds.
    """

    def run_setup(self):
        return succeed(None)

    def make_request(self):
        return succeed(None)

    def run_cleanup(self):
        return succeed(None)


class RequestMeasureTests(TestCase):
    """
    Tests for ``_request_and_measure``.
    """

    def test_single_count(self):
        """
        Adds ``request_rate`` samples per call.
        """
        calls_per_second = 10
        clock = Clock()
        request = TestRequest()
        scenario = RequestLoadScenario(
            clock, request, request_rate=calls_per_second
        )
        scenario._request_and_measure(1)
        self.assertEqual(
            scenario.rate_measurer.get_metrics()['ok_count'], calls_per_second
        )

    def test_multiple_count(self):
        """
        The count controls how many requests are made.
        """
        calls_per_second = 10
        seconds = 2
        clock = Clock()
        request = TestRequest()
        scenario = RequestLoadScenario(
            clock, request, request_rate=calls_per_second
        )
        scenario._request_and_measure(seconds)
        self.assertEqual(
            scenario.rate_measurer.get_metrics()['ok_count'],
            calls_per_second * seconds
        )
