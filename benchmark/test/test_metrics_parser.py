# Copyright 2016 ClusterHQ Inc.  See LICENSE file for details.

from benchmark.metrics_parser import (
    mean, container_convergence, cpu_usage_for_process,
    wallclock_for_operation, request_latency
)
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

    def test_cpu_usage_for_process_no_matching_results(self):
        """
        cputime_for_process only considers results which have the
        'cputime' metric type and match the specified process name.
        None is returned if no results match.
        """
        process_name = 'test-process'
        results = [
            {
                'metric': {
                    'type': 'wallclock'
                },
                'process': process_name
            },
            {
                'metric': {
                    'type': 'cputime'
                },
                'process': 'another-process'
            },
        ]
        cputime_result = cpu_usage_for_process(results, process_name)
        self.assertEqual(cputime_result, None)

    def test_cpu_usage_for_process_calculates_result(self):
        """
        cputime_for_process correctly calculates the mean CPU percentage
        for a process by dividing the cputime by the wallclock time for
        each sample
        """
        process_name = 'test-process'
        results = [
            {
                'metric': {
                    'type': 'cputime'
                },
                'process': process_name,
                'value': 10,
                'wallclock': 50
            },
            {
                'metric': {
                    'type': 'cputime'
                },
                'process': process_name,
                'value': 30,
                'wallclock': 100
            },
        ]
        cputime_result = cpu_usage_for_process(results, process_name)
        self.assertEqual(cputime_result, 0.25)

    def test_wallclock_for_operation_no_matching_results(self):
        """
        wallclock_for_operation only considers results which have the
        'wallclock' metrics and match the specified operation name.
        None is returned if no results match.
        """
        operation_name = 'test-operation'
        results = [
            {
                'metric': {
                    'type': 'wallclock'
                },
                'operation': {
                    'type': 'another-operation'
                }
            },
            {
                'metric': {
                    'type': 'cputime'
                },
                'operation': {
                    'type': operation_name
                }
            },
        ]
        wallclock_result = wallclock_for_operation(results, operation_name)
        self.assertEqual(wallclock_result, None)

    def test_wallclock_for_operation_calculates_result(self):
        """
        wallclock_for_process returns the mean of the values from
        samples which have the 'wallclock' metric type and match the
        specified operation.
        """
        operation = 'test-operation'
        results = [
            {
                'metric': {
                    'type': 'wallclock'
                },
                'operation': {
                    'type': operation
                },
                'value': 11
            },
            {
                'metric': {
                    'type': 'wallclock'
                },
                'operation': {
                    'type': operation
                },
                'value': 14
            },
        ]
        wallclock_result = wallclock_for_operation(results, operation)
        self.assertEqual(wallclock_result, 12.5)

    def test_container_convergence_no_matching_results(self):
        """
        container_convergence only considers results which have the
        'wallclock' metric and are for the 'create-container' operation.
        None is returned if no results match.
        """
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
        """
        container_convergence returns the percentage of
        'create-container' operations that completed within the
        specified time limit.
        """
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
                'value': 2
            },
            {
                'metric': {
                    'type': 'wallclock'
                },
                'operation': {
                    'type': 'create-container'
                },
                'value': 5
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
        self.assertEqual(convergence_results, 0.75)

    def test_request_latency_no_matching_results(self):
        """
        request_latency only considers results which have the
        'scenario.metrics.call_durations' property.
        None is returned if no results match.
        """
        results = [
            {
                'scenario': {
                    'name': 'test-scenario',
                    'type': 'test-scenario-type'
                },
            },
            {
                'scenario': {
                    'name': 'test-scenario',
                    'type': 'test-scenario-type',
                    'metrics': {}
                },
            }
        ]
        latency_result = request_latency(results, 10)
        self.assertEqual(latency_result, None)

    def test_request_latency_calculates_result(self):
        """
        request_latency correctly calculates the percentage of scenario
        requests that complete within the specified time limit.
        """
        results = [
            {
                'scenario': {
                    'name': 'test-scenario',
                    'type': 'test-scenario-type',
                    'metrics': {
                        'call_durations': {
                            '1.0': 10,
                            '0.8': 10,
                            '0.9': 10,
                            '1.1': 10,
                            '0.7': 10
                        },
                        'ok_count': 50,
                        'err_count': 0,
                    }
                },
            },
            {
                'scenario': {
                    'name': 'test-scenario',
                    'type': 'test-scenario-type',
                    'metrics': {
                        'call_durations': {
                            '1.0': 10,
                            '0.8': 10,
                            '0.9': 10,
                            '1.1': 10,
                            '0.7': 10
                        },
                        'ok_count': 40,
                        'err_count': 10,
                    }
                },
            }
        ]
        latency_result = request_latency(results, 1)
        # 20/100 requests took more that 1 second.
        self.assertEqual(latency_result, 0.8)
