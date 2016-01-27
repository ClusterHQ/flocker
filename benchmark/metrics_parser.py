# Copyright ClusterHQ Inc.  See LICENSE file for details.

import argparse
import json
from collections import defaultdict

example = {"flocker_control":6,
           "-- WALL --":101.2}

def apply_cpu_metric(result_blob):
    wall_time = float(result_blob.get(u'-- WALL --'))
    for k, v in result_blob.iteritems():
        if not k == u'-- WALL --':
            result_blob[k] = v/wall_time

def add_results_to_table(result, result_table):
    for k, v in result.iteritems():
        result_table[k].append(v)


def print_averages(results):
    print "Results for benchmarking:"
    for process, result in results.iteritems():
        s = "{process}: {result}".format(
            process=process,
            result=sum(result) / len(result)
        )
        print s


def parse_args(args):
    parser = argparse.ArgumentParser(
        description="Produce CSV from benchmarking results"
    )
    parser.add_argument("files", nargs="*", type=argparse.FileType(),
                        help="Input JSON files to be processed")

    return parser.parse_args(args).files

def main(args):
    files = parse_args(args)

    for f in files:
        results = json.load(f)
        # XXX adding schema json validation
        result_table = defaultdict(list)
        for sample in results[u'samples']:
            for result in sample[u'value'].itervalues():
                apply_cpu_metric(result)
                add_results_to_table(result, result_table)

        print result_table
        print_averages(result_table)
