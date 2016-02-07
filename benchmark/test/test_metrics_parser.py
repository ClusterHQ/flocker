# Copyright 2016 ClusterHQ Inc.  See LICENSE file for details.

from benchmark.metrics_parser import mean, container_convergence
from flocker.testtools import TestCase


class MetricsParserTests(TestCase):
    """
    Tests for the metrics parsing script.
    """

    def test_mean_returns_floating_point_number(self):
        values = [1, 2, 3, 4]
        mean_result = mean(values)
        self.assertIsInstance(mean_result, float)

    def test_mean_returns_none_for_no_values(self):
        values = []
        self.assertEqual(mean(values), None)

    def test_mean_correctly_calculates_mean(self):
        values = [1, 2, 3, 4, 5, 6]
        self.assertEqual(mean(values), 3.5)

    def test_container_convergence_returns_none_when_no_relevant_results(self):
        results = [
            {
                'metric': {
                    'type': 'cputime'
                },
                'operation': {
                    'type': 'create-container'
                },
                'value': 4
            },
            {
                'metric': {
                    'type': 'wallclock'
                },
                'operation': {
                    'type': 'read-request'
                },
                'value': 10,
            },
        ]

        convergence_results = container_convergence(results, 10)
        self.assertEqual(convergence_results, None)

    def test_container_convergence_calculates_result(self):
        results = [
            {
                'metric': {
                    'type': 'wallclock'
                },
                'operation': {
                    'type': 'create-container'
                },
                'value': 4
            },
            {
                'metric': {
                    'type': 'wallclock'
                },
                'operation': {
                    'type': 'create-container'
                },
                'value': 9,
            },
        ]
        convergence_results = container_convergence(results, 5)
        self.assertEqual(convergence_results, 0.5)
