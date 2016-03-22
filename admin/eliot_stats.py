# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
Print a summary of the time taken for each Eliot action.

E.g.

admin/eliot-stats \
    --resample-period 5min \
    --action-type-prefix 'flocker:node:' \
     <(zcat flocker-dataset-agent_eliot.gz | admin/filter-eliot | jq -s -c .)

Where ``flocker-dataset-agent_eliot`` has been extracted from a
``flocker-diagnostics`` archive.
"""
from functools import partial
import sys

import numpy
import pandas

from twisted.python.filepath import FilePath
from twisted.python.usage import Options, UsageError


class EliotStatsOptions(Options):
    optParameters = [
        ['action-type-prefix', None, u"",
         'Only look for actions with this prefix', unicode],
        ['resample-period', None, u"5min",
         'Resample to this time period.', unicode],
    ]

    def parseArgs(self, logfile_path):
        self["logfile_path"] = FilePath(logfile_path)


def eliot_stats_main(args, top_level, base_path):
    options = EliotStatsOptions()
    try:
        options.parseOptions(args)
    except UsageError as e:
        sys.stderr.write("%s: %s\n" % (base_path.basename(), e))
        raise SystemExit(1)

    data = pandas.read_json(options["logfile_path"].path)

    # Actions only
    data = data[data.action_type.notnull()]
    data = data[
        data.action_type.str.startswith(
            options["action-type-prefix"]
        )
    ]
    # Make task level parent a column so that we can group on task level.
    # Otherwise the action end message can't be matched with the start.
    data['task_level_parent'] = data.task_level.map(
        lambda v: tuple(map(str, v[:-1]))
    )
    # Limit the columns
    data = data[
        ["task_uuid", "task_level_parent",
         "action_type", "action_status",
         "timestamp"]
    ]

    # Get the unique action_status values in this dataset
    action_status_values = data.action_status.unique()

    # Turn action_status values into columns
    data = pandas.pivot_table(
        data,
        # This is where I start to lose the plot. I'm putting these in the
        # index so that I don't lose them. I'd rather they were just columns
        # alongside the new "started, succeeded, failed" columns but not sure
        # how to do that.
        index=["task_uuid", "task_level_parent", "action_type"],
        columns="action_status",
        values="timestamp",
        aggfunc=max
    )
    # And here we make the index items back in to colums...
    # https://stackoverflow.com/questions/20461165/how-to-convert-pandas-index-in-a-dataframe-to-a-column
    data = data.reset_index()

    # There should only ever be succeeded or failed.
    # Unfortunately, maximum returns NaT if one is found, so replace those with
    # 0 (the unix epoch).
    # There may not be any failures, but if there are, check both failed and
    # succeeded columns for the end time.
    end_time = numpy.maximum(*tuple(
        data[key].values
        for key in action_status_values
    ))
    data["duration"] = end_time - data.started
    data["success"] = data.succeeded != pandas.NaT
    data["failure"] = data.succeeded == pandas.NaT

    # Sort by start time.
    data = data.sort_index(by=["started"])

    # Maybe this would be enough on its own.
    data = data.set_index(keys=["started"])

    data = data[["action_type", "duration", "success", "failure", "succeeded"]]

    data = data.resample(options["resample-period"]).apply({
        u"action_type": lambda v: ','.join(x.split(":")[-1] for x in set(v)),
        u"duration": "sum",
        u"success": partial(numpy.sum, dtype=numpy.int),
        u"failure": partial(numpy.sum, dtype=numpy.int),
    })

    print data.to_string()
    return data
