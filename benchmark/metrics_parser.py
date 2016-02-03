# Copyright ClusterHQ Inc.  See LICENSE file for details.

import argparse
from collections import defaultdict
import csv
import itertools
import json

itertools.groupby

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


def filter_results(results, attribute, attribute_value):
    return [
        r for r in results
        if r['control_service'][attribute] == attribute_value
    ]


def filter_results_scenario(results, scenario):
    return [r for r in results if r['scenario']['name'] == scenario]


def control_service_attribute(results, key):
    """
    Extract all unique results from the "control_service" section
    that contain a particular key.
    """
    counts = [r['control_service'][key] for r in results]
    return list(set(counts))


def scenario_attribute(results):
    """
    Extract all unique scenarios that are available in the results.
    """
    scenarios = [r['scenario']['name'] for r in results]
    return list(set(scenarios))


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
        lambda r: r['metric']['type'] == 'wallclock'
        and r['operation']['type'] == operation,
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
        r for r in results if r['metric']['type'] == 'wallclock'
        and r['operation']['type'] == 'create-container'
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
        r['scenario'] for r in results
        if r['scenario'].get('metrics')
        and r['scenario']['metrics'].get('call_durations')
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


def flatten(results):
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


def extract_results(all_results):
    summary = defaultdict(list)
    node_counts = control_service_attribute(all_results, 'node_count')
    container_counts = control_service_attribute(
        all_results, 'container_count'
    )
    versions = control_service_attribute(all_results, 'flocker_version')
    scenarios = scenario_attribute(all_results)
    for node_count, container_count, version, scenario in itertools.product(
        node_counts, container_counts, versions, scenarios
    ):
        results = filter_results(all_results, 'node_count', node_count)
        results = filter_results(results, 'container_count', container_count)
        results = filter_results(results, 'flocker_version', version)
        results = filter_results_scenario(results, scenario)
        if len(results) > 0:
            result = {
                u'Flocker Version': version,
                u'Nodes': node_count,
                u'Containers': container_count,
                u'Scenario': scenario,
                u'Control Service CPU': cputime_for_process(
                    results, 'flocker-control'
                ),
                u'Dataset Agent CPU': cputime_for_process(
                    results, 'flocker-dataset'
                ),
                u'Container Agent CPU': cputime_for_process(
                    results, 'flocker-contain'
                ),
                u'Containers Converged Within Limit': container_convergence(
                    results, 60
                ),
                u'Scenario Requests Within Limit': request_latency(
                    results, 30
                ),
            }
            summary[scenario].append(result)
    return summary


def parse_args(args):
    parser = argparse.ArgumentParser(
        description="Produce CSV from benchmarking results"
    )
    parser.add_argument("files", nargs="*", type=argparse.FileType(),
                        help="Input JSON files to be processed")

    return parser.parse_args(args).files


def main(args):
    files = parse_args(args)
    results = []
    for f in files:
        results.extend(flatten(json.load(f)))
    results = extract_results(results)

    for scenario, result in results.iteritems():
        write_csv(result, 'results-{}.csv'.format(scenario))
