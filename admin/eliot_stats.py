# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
Print a summary of the time taken for each Eliot action.

E.g.

./admin/eliot-stats <(jq -s -c . clusterhq_flocker_logs_107de224-ed6e-11e5-8ab6-029e8f8dc7b7/flocker-dataset-agent_eliot)

Where
``clusterhq_flocker_logs_107de224-ed6e-11e5-8ab6-029e8f8dc7b7/flocker-dataset-agent_eliot``
has been extracted from a ``flocker-diagnostics`` archive.
"""

import numpy
import pandas


def eliot_stats_main(args, top_level, base_path):
    data = pandas.read_json(args[0])
    # Actions only
    data = data[data.action_type.notnull()]
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
    # Turn action_status values into columns
    data = pandas.pivot_table(
        data,
        index=["task_uuid", "task_level_parent", "action_type"],
        columns="action_status",
        values="timestamp",
        aggfunc=max
    )
    # There should only ever be succeeded or failed.
    # Unfortunately, maximum returns NaT if one is found, so replace those with
    # 0 (the unix epoch).
    end_time = numpy.maximum(
        data.succeeded.fillna(0),
        data.failed.fillna(0)
    )
    data["duration"] = end_time - data.started
    data["succeeded"] = data.succeeded.notnull()
    print data[["started", "duration", "succeeded"]].to_string()
