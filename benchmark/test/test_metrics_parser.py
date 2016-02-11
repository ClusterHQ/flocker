# Copyright 2016 ClusterHQ Inc.  See LICENSE file for details.

from benchmark.metrics_parser import (
    mean, container_convergence, cpu_usage_for_process,
    wallclock_for_operation, request_latency, handle_cputime_metric,
    handle_wallclock_metric
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
        cputime_for_process correctly calculates the CPU percentage for
        a process by dividing the total cputime by the total wallclock
        time across all the samples.
        """
        process_name = 'test-process'
        results = [
            {
                'metric': {
                    'type': 'cputime'
                },
                'process': process_name,
                'value': 10,
                'wallclock': 60
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
        # Total CPU time: 40
        # Total wallclock time: 160
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

    def test_handle_cputime_metric_creates_multiple_samples(self):
        """
        handle_cputime_metric creates multiple sample objects, each with
        one value, from a single sample containing many values. It does
        not create a sample object from the '-- WALL --' key but adds
        this value to every other sample.
        """
        wallclock_key = '-- WALL --'
        common_props = {
            'version': '1.10.1',
            'scenario': 'default'
        }
        sample = {
            'value': {
                '10.0.0.1': {
                    'process1': 3,
                    wallclock_key: 102.123
                },
                '10.0.0.2': {
                    'process1': 2,
                    'process2': 5,
                    wallclock_key: 124.462
                }
            }
        }

        expected_samples = [
            {'process': 'process1', 'value': 3, 'wallclock': 102.123},
            {'process': 'process1', 'value': 2, 'wallclock': 124.462},
            {'process': 'process2', 'value': 5, 'wallclock': 124.462},
        ]

        for s in expected_samples:
            s.update(common_props)

        samples = handle_cputime_metric(common_props, sample)
        self.assertEqual(samples, expected_samples)

    def test_handle_wallclock_metrics_creates_sample(self):
        """
        handle_wallclock_metric returns a list containing a single
        sample object with the value from the original sample.
        """
        common_props = {
            'version': '1.10.1',
            'scenario': 'default'
        }
        sample = {
            'value': 12
        }
        expected_samples = [
            {'value': 12}
        ]
        for s in expected_samples:
            s.update(common_props)

        samples = handle_wallclock_metric(common_props, sample)
        self.assertEqual(samples, expected_samples)
