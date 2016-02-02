# Copyright ClusterHQ Inc.  See LICENSE file for details.

import argparse
import csv
import itertools
import json


WALL_CLOCK_KEY = u'-- WALL --'


HEADERS = [
    u'FlockerVersion',
    u'Nodes',
    u'Containers',
    u'ControlServiceCPUSteady',
    u'DatasetAgentCPUSteady',
    u'ContainerAgentCPUSteady',
    u'ControlServiceCPUReadLoad',
    u'DatasetAgentCPUReadLoad',
    u'ContainerAgentCPUReadLoad',
    u'RequestsWithinLimitReadLoad',
    u'ControlServiceCPUWriteLoad',
    u'DatasetAgentCPUWriteLoad',
    u'ContainerAgentCPUWriteLoad',
    u'RequestsWithinLimitWriteLoad',
    u'ContainerAdditionConvergence',
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


def control_service_attribute(results, key):
    """
    Extract all unique results from the "control_service" section
    that contain a particular key.
    """
    counts = [r['control_service'][key] for r in results]
    return list(set(counts))


def mean(values):
    if len(values) > 0:
        return sum(values) / len(values)
    return None


def cputime_for_process(results, process, scenario, fn=mean):
    """
    Calculate the CPU time for a process running in a particular scenario.

    By default this will return the `mean` result.
    """
    process_results = itertools.ifilter(
        lambda r: r['metric']['type'] == 'cputime'
        and r['process'] == process
        and r['scenario']['type'] == scenario,
        results
    )
    values = [r['value'] / r['wallclock'] for r in process_results]
    return fn(values)


def wallclock_for_operation(results, operation, fn=mean):
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
    return fn(values)


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


def request_latency(results, scenario, seconds):
    """
    Calculate the percentage of scenario requests have a latency under the
    specified time limit.
    """
    scenario_results = [
        r['scenario'] for r in results
        if r['scenario']['type'] == scenario
        and r['scenario'].get('metrics')
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
            total_requests += (
                metric['ok_count'] + metric['err_count']
            )
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
    summary = []
    node_counts = control_service_attribute(all_results, 'node_count')
    container_counts = control_service_attribute(
        all_results, 'container_count'
    )
    versions = control_service_attribute(all_results, 'flocker_version')
    for node_count, container_count, version in itertools.product(
        node_counts, container_counts, versions
    ):
        results = filter_results(all_results, 'node_count', node_count)
        results = filter_results(results, 'container_count', container_count)
        results = filter_results(results, 'flocker_version', version)
        if len(results) > 0:
            result = {
                u'FlockerVersion': version,
                u'Nodes': node_count,
                u'Containers': container_count,
                u'ControlServiceCPUSteady': cputime_for_process(
                    results, 'flocker-control', 'no-load'
                ),
                u'ControlServiceCPUReadLoad': cputime_for_process(
                    results, 'flocker-control', 'read-request-load'
                ),
                u'ControlServiceCPUWriteLoad': cputime_for_process(
                    results, 'flocker-control', 'write-request-load'
                ),
                u'DatasetAgentCPUSteady': cputime_for_process(
                    results, 'flocker-dataset', 'no-load'
                ),
                u'DatasetAgentCPUReadLoad': cputime_for_process(
                    results, 'flocker-dataset', 'read-request-load'
                ),
                u'DatasetAgentCPUWriteLoad': cputime_for_process(
                    results, 'flocker-dataset', 'write-request-load'
                ),
                u'ContainerAgentCPUSteady': cputime_for_process(
                    results, 'flocker-contain', 'no-load'
                ),
                u'ContainerAgentCPUReadLoad': cputime_for_process(
                    results, 'flocker-contain', 'read-request-load'
                ),
                u'ContainerAgentCPUWriteLoad': cputime_for_process(
                    results, 'flocker-contain', 'write-request-load'
                ),
                u'ContainerAdditionConvergence': container_convergence(
                    results, 60
                ),
                u'RequestsWithinLimitReadLoad': request_latency(
                    results, 'read-request-load', 30
                ),
                u'RequestsWithinLimitWriteLoad': request_latency(
                    results, 'write-request-load', 30
                ),
            }
            summary.append(result)
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
    write_csv(extract_results(results), 'results.csv')
