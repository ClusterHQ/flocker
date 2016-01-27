# Copyright ClusterHQ Inc.  See LICENSE file for details.

import json
from collections import defaultdict

example = {"flocker_control":6,
           "-- WALL --":101.2}

def apply_cpu_metric(result_blob):
    wall_time = float(result_blob.get(u'-- WALL --'))
    #result_blob.remove(u'--WALL--')
    for k, v in result_blob.iteritems():
        if not k == u'-- WALL --':
            result_blob[k] = v/wall_time

def add_results_to_table(result, result_table):
    for k, v in result.iteritems():
        result_table[k].append(v)


def main(args):
    for json_file in args:
        with open(json_file) as f:
            results = json.load(f)
            # XXX adding schema json validation
            result_table = defaultdict(list)
            for sample in results[u'samples']:
                for result in sample[u'value'].itervalues():
                    apply_cpu_metric(result)
                    add_results_to_table(result, result_table)

            print result_table
