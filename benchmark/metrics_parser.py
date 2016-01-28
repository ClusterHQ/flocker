# Copyright ClusterHQ Inc.  See LICENSE file for details.

import argparse
import csv
import json


WALL_CLOCK_KEY = u'-- WALL --'


HEADERS = [
    u'FlockerVersion',
    u'Nodes',
    u'Containers',
    u'ControlServiceCPUSteady',
    u'CombinedAgentCPUSteady',
    u'ControlServiceCPUReadLoad',
    u'CombinedAgentCPUReadLoad',
    u'ControlServiceCPUWriteLoad',
    u'CombinedAgentCPUWriteLoad',
    u'ContainerAdditionConvergence',
]


def write_csv(results, filename):
    with open(filename, 'w') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=HEADERS, restval='N/A')
        writer.writeheader()
        writer.writerows(results)


def print_averages(results):
    print "Results for benchmarking:"
    for process, result in results.iteritems():
        s = "{process}: {result}".format(
            process=process,
            result=sum(result) / len(result)
        )
        print s


def flatten(results):
    flattened = []
    common = dict(
        [(k, results.get(k)) for k in results.iterkeys() if k != 'samples']
    )

    metric_type = results['metric']['type']

    for sample in results['samples']:
        if metric_type  == 'cputime':
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

    return parser.parse_args(args).files


def main(args):
    files = parse_args(args)
    results = []
    for f in files:
        results.extend(flatten(json.load(f)))
