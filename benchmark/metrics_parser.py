# Copyright ClusterHQ Inc.  See LICENSE file for details.

import argparse
from collections import defaultdict
import csv
import itertools
import json


WALL_CLOCK_KEY = u'-- WALL --'
HEADERS = [
    u'Flocker Version',
    u'Nodes',
    u'Containers',
    u'Scenario',
    u'Control Service CPU',
    u'Dataset Agent CPU',
    u'Container Agent CPU',
    u'Containers Converged Within Limit',
    u'Scenario Requests Within Limit',
]


def write_csv(results, filename):
    with open(filename, 'w') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(results)


def mean(values):
    if len(values) > 0:
        return sum(values) / len(values)
    return None


def cputime_for_process(results, process):
    """
    Calculate the CPU time for a process running in a particular scenario.

    By default this will return the `mean` result.
    """
    process_results = itertools.ifilter(
        lambda r: r['metric']['type'] == 'cputime' and r['process'] == process,
        results
    )
    values = [r['value'] / r['wallclock'] for r in process_results]
    return mean(values)


def wallclock_for_operation(results, operation):
    """
    Calculate the wallclock time for a process running in a particular
    scenario.

    By default this will return the `mean` result.
    """
    operation_results = itertools.ifilter(
        lambda r: r['metric']['type'] == 'wallclock' and
        r['operation']['type'] == operation,
        results
    )
    values = [r['value'] for r in operation_results]
    return mean(values)


def container_convergence(results, seconds):
    """
    Calculate the percentage of containers that converge within a given
    time period.
    """
    convergence_results = [
        r for r in results if r['metric']['type'] == 'wallclock' and
        r['operation']['type'] == 'create-container'
    ]
    num_convergences = len(convergence_results)
    if num_convergences > 0:
        convergences_within_limit = [
            r for r in convergence_results if r['value'] < seconds
        ]
        return len(convergences_within_limit) / num_convergences

    return None


def request_latency(results, seconds):
    """
    Calculate the percentage of scenario requests have a latency under the
    specified time limit.
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
            for k, v in metric['call_durations'].iteritems():
                if float(k) < seconds:
                    requests_under_limit += v
            total_requests += metric['ok_count'] + metric['err_count']
        return requests_under_limit / total_requests
    return None


class BenchmarkingResults(object):
    """
    Processes benchmarking results and produces reports.
    """
    def __init__(self):
        self.results = []

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
        for scenario, result in summary.iteritems():
            filename = '{prefix}-{scenario}.csv'.format(
                prefix=prefix, scenario=scenario
            )
            write_csv(result, filename)

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
                result = {
                    u'Flocker Version': version,
                    u'Nodes': node,
                    u'Containers': container,
                    u'Scenario': scenario,
                    u'Control Service CPU':
                        cputime_for_process(results, 'flocker-control'),
                    u'Dataset Agent CPU':
                        cputime_for_process(results, 'flocker-dataset'),
                    u'Container Agent CPU':
                        cputime_for_process(results, 'flocker-contain'),
                    u'Containers Converged Within Limit':
                        container_convergence(results, 60),
                    u'Scenario Requests Within Limit':
                        request_latency(results, 30),
                }
                summary[scenario].append(result)
        return summary

    def _flatten(self, results):
        """
        Flatten a set of results by creating a separate object for each
        sample in the results.
        """
        flattened = []
        common = dict(
            [(k, results.get(k)) for k in results.iterkeys() if k != 'samples']
        )

        metric_type = results['metric']['type']

        for sample in results['samples']:
            if sample['success']:
                if metric_type == 'cputime':
                    for ip, data in sample['value'].iteritems():
                        wall_time = data[WALL_CLOCK_KEY]
                        for process, value in data.iteritems():
                            if process != WALL_CLOCK_KEY:
                                doc = dict(common)
                                doc['node_ip'] = ip
                                doc['process'] = process
                                doc['value'] = value
                                doc['wallclock'] = wall_time
                                flattened.append(doc)
                elif metric_type == 'wallclock':
                    doc = dict(common)
                    doc['value'] = sample['value']
                    flattened.append(doc)
        return flattened


def parse_args(args):
    parser = argparse.ArgumentParser(
        description="Produce CSV from benchmarking results"
    )
    parser.add_argument("files", nargs="*", type=argparse.FileType(),
                        help="Input JSON files to be processed")

    parser.add_argument("--output-file-prefix", nargs='?', type=str,
                        dest='prefix', default="results",
                        help="Prefix to to be used for the output files")
    parsed_args = parser.parse_args(args)
    return parsed_args.files, parsed_args.prefix


def main(args):
    files, prefix = parse_args(args)

    br = BenchmarkingResults()
    for f in files:
        try:
            result = json.load(f)
            br.add_results(result)
        except ValueError:
            print "Could not decode JSON from file: ", f.name
    br.output_csv(prefix)
