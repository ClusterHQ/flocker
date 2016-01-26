# Copyright ClusterHQ Inc.  See LICENSE file for details.

import json
from collections import defaultdict

example_resultxs = {
    "master": [
        {
            "num_nodes": 10,
            "num_containers": 10,
            "metrics": [
                {
                    "cpu_no_load": 0.145
                }
            ]
        },
    ]
}


def combine_metrics(metrics):
    combined_metrics = defaultdict(list)
    for metric in metrics:
        for k, v in metric[u'value'].iteritems():
            combined_metrics[k].append(v)
    print combined_metrics


def get_branch_results(results):
    parsed_results = {}
    for result in results:
        version = result[u'control_service'][u'flocker_version']
        # num_nodes = result[u'control_service'][u'num_nodes']
        # num_containers = result[u'control_service'][u'num_containers']
        combine_metrics(result[u'samples'])
    return parsed_results


def main(args):
    results = []
    for arg in args:
        with open(arg) as f:
            results.append(json.load(f))
    get_branch_results(results)
