# Copyright 2016 ClusterHQ Inc.  See LICENSE file for details.

import argparse
from collections import defaultdict, OrderedDict
import csv
import itertools
import json
import sys


def write_csv(results, headers, filename):
    """
    Write a set of results to a CSV file.
    """
    with open(filename, 'w') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=headers)
        writer.writeheader()
        writer.writerows(results)


def mean(values):
    """
    Calculate the mean for a set of values.

    :param values: Values to calculate the mean of.
    """
    if len(values) > 0:
        return float(sum(values)) / len(values)
    return None


def cpu_usage_for_process(results, process):
    """
    Calculate the CPU percentage for a process running in a particular
    scenario.

    :param results: Results to extract values from.
    :param process: Process name to calculate CPU usage for.
    """
    process_results = [
        r for r in results if r['metric']['type'] == 'cputime' and
        r['process'] == process
    ]

    cpu_values = sum(r['value'] for r in process_results)
    wallclock_values = sum(r['wallclock'] for r in process_results)

    if wallclock_values > 0:
        return float(cpu_values) / wallclock_values
    return None


def wallclock_for_operation(results, operation):
    """
    Calculate the wallclock time for a process running in a particular
    scenario.

    :param results: Results to extract values from.
    :param operation: Operation name to calculate wallclock results for.

    :return: The mean wallclock time observed.
    """
    operation_results = itertools.ifilter(
        lambda r: r['metric']['type'] == 'wallclock' and
        r['operation']['type'] == operation,
        results
    )
    values = [r['value'] for r in operation_results]
    return mean(values)


def container_convergence(results, limit):
    """
    Calculate the percentage of containers that converge within a given
    time period.

    :param results: Results to extract values from.
    :param limit: Time limit for container convergence in seconds.
    """
    convergence_results = [
        r for r in results if r['metric']['type'] == 'wallclock' and
        r['operation']['type'] == 'create-container'
    ]
    num_convergences = len(convergence_results)
    if num_convergences > 0:
        convergences_within_limit = [
            r for r in convergence_results if r['value'] <= limit
        ]
        return float(len(convergences_within_limit)) / num_convergences

    return None


def request_latency(results, limit):
    """
    Calculate the percentage of scenario requests have a latency under the
    specified time limit.

    :param results: Results to extract values from.
    :param limit: Request latency limit in seconds.
    """
    scenario_results = [
        r['scenario'] for r in results if r['scenario'].get('metrics') and
        r['scenario']['metrics'].get('call_durations')
    ]

    if len(scenario_results) > 0:
        unique_metrics = []
        for result in scenario_results:
            if result['metrics'] not in unique_metrics:
                unique_metrics.append(result['metrics'])

        total_requests = 0
        requests_under_limit = 0
        for metric in unique_metrics:
            for duration, num_requests in metric['call_durations'].iteritems():
                if float(duration) <= limit:
                    requests_under_limit += num_requests
            total_requests += metric['ok_count'] + metric['err_count']
        return float(requests_under_limit) / total_requests
    return None


def handle_cputime_metric(common_props, sample):
    """
    Create a sample object for a 'cputime' metric sample.

    :param common_props: Common properties shared with all other samples.
    :param sample: Original sample to extract values from.

    :return list: The created samples.
    """
    cputime_samples = []

    wallclock_key = u'-- WALL --'
    for data in sample['value'].itervalues():
        wall_time = data[wallclock_key]
        for process, value in data.iteritems():
            if process != wallclock_key:
                cputime_sample = dict(common_props)
                cputime_sample['process'] = process
                cputime_sample['value'] = value
                cputime_sample['wallclock'] = wall_time
                cputime_samples.append(cputime_sample)

    return cputime_samples


def handle_wallclock_metric(common_props, sample):
    """
    Create a sample object for a 'wallclock' metric sample.

    :param common_props: Common properties shared with all other samples.
    :param sample: Original sample to extract values from.

    :return list: The created samples.
    """
    wallclock_samples = []
    wallclock_sample = dict(common_props)
    wallclock_sample['value'] = sample['value']
    wallclock_samples.append(wallclock_sample)
    return wallclock_samples


METRIC_HANDLER = {
    'cputime': handle_cputime_metric,
    'wallclock': handle_wallclock_metric,
}


class BenchmarkingResults(object):
    """
    Processes benchmarking results and produces reports.
    """
    def __init__(self, convergence_limit, latency_limit):
        self.results = []
        self.convergence_limit = convergence_limit
        self.latency_limit = latency_limit

    def add_results(self, results):
        """
        Add a set of results to the existing results.
        """
        self.results.extend(self._flatten(results))

    def output_csv(self, prefix):
        """
        Output a CSV representation of a set of results.
        """
        summary = self._create_summary()
        for scenario, results in summary.iteritems():
            filename = '{prefix}-{scenario}.csv'.format(
                prefix=prefix, scenario=scenario
            )
            headers = []
            for key in itertools.chain(*results):
                if key not in headers:
                    headers.append(key)
            write_csv(results, headers, filename)

    def _versions(self):
        """
        Return all unique versions present in the results.
        """
        versions = [
            r['control_service']['flocker_version'] for r in self.results
        ]
        return set(versions)

    def _node_counts(self):
        """
        Return all unique node counts present in the results.
        """
        nodes = [r['control_service']['node_count'] for r in self.results]
        return set(nodes)

    def _container_counts(self):
        """
        Return all unique container counts present in the results.
        """
        containers = [
            r['control_service']['container_count'] for r in self.results
        ]
        return set(containers)

    def _scenarios(self):
        """
        Return all unique scenarios present in the results.
        """
        scenarios = [r['scenario']['name'] for r in self.results]
        return set(scenarios)

    def _filter_results(self, node_count, container_count, version, scenario):
        """
        Extract results which match the specified number of nodes,
        number of containers, Flocker version and benchmarking scenario.
        """
        return [r for r in self.results
                if r['control_service']['node_count'] == node_count and
                r['control_service']['container_count'] == container_count and
                r['control_service']['flocker_version'] == version and
                r['scenario']['name'] == scenario]

    def _create_summary(self):
        """
        Summarise the results.

        For each scenario, include the CPU usage for each process,
        the percentage of containers that converge within a given time
        limit and the percentage of scenario requests that complete
        within a given time limit.
        """
        summary = defaultdict(list)
        node_counts = self._node_counts()
        container_counts = self._container_counts()
        versions = self._versions()
        scenarios = self._scenarios()
        for node, container, version, scenario in itertools.product(
                node_counts, container_counts, versions, scenarios
        ):
            results = self._filter_results(
                node, container, version, scenario
            )
            if len(results) > 0:
                result = OrderedDict()
                result['Flocker Version'] = version
                result['Nodes'] = node
                result['Containers'] = container
                result['Scenario'] = scenario
                result['Control Service CPU'] = cpu_usage_for_process(
                    results, 'flocker-control'
                )
                result['Dataset Agent CPU'] = cpu_usage_for_process(
                    results, 'flocker-dataset'
                )
                result['Container Agent CPU'] = cpu_usage_for_process(
                    results, 'flocker-contain'
                )
                convergence_key = (
                    'Containers converged within {seconds} seconds'.format(
                        seconds=self.convergence_limit
                    )
                )
                result[convergence_key] = container_convergence(
                    results, self.convergence_limit
                )

                request_latency_key = (
                    'Scenario requests within {seconds} seconds'.format(
                        seconds=self.latency_limit
                    )
                )
                result[request_latency_key] = request_latency(
                    results, self.latency_limit
                )
                summary[scenario].append(result)
        return summary

    @staticmethod
    def _flatten(results):
        """
        Flatten a set of results by creating a separate object for each
        sample in the results.
        """
        flattened = []
        common_props = dict(
            [(k, results.get(k)) for k in results.iterkeys() if k != 'samples']
        )

        metric_type = results['metric']['type']

        for sample in results['samples']:
            if sample['success']:
                flattened.extend(
                    METRIC_HANDLER[metric_type](common_props, sample)
                )
        return flattened


def parse_args(args):
    """
    Parse command line arguments.
    """
    parser = argparse.ArgumentParser(
        description="Produce CSV from benchmarking results"
    )
    parser.add_argument("files", nargs="*", type=argparse.FileType(),
                        help="Input JSON files to be processed")

    parser.add_argument("--output-file-prefix", nargs='?', type=str,
                        dest='prefix', default="results",
                        help="Prefix to be used for the output files")
    parser.add_argument("--convergence-limit, -c", nargs='?', type=int,
                        dest='convergence_limit', default=60,
                        help="Container convergence limit in seconds")
    parser.add_argument("--request-latency-limit, -r", nargs='?', type=int,
                        dest='latency_limit', default=30,
                        help="Request latency limit in seconds")
    parsed_args = parser.parse_args(args)

    if not parsed_args.files:
        parser.print_help()
        sys.exit(1)

    return parsed_args


def main(args):
    parsed_args = parse_args(args)
    results = BenchmarkingResults(
        parsed_args.convergence_limit, parsed_args.latency_limit
    )
    for input_file in parsed_args.files:
        try:
            result = json.load(input_file)
            results.add_results(result)
        except ValueError:
            print "Could not decode JSON from file: ", input_file.name
    results.output_csv(parsed_args.prefix)
