# Copyright ClusterHQ Inc.  See LICENSE file for details.
"""
Run a command on every node in a benchmark or acceptance testing cluster.

E.g.

./admin/cluster-command --config-file=$PWD/managed.yaml -- shutdown -h now

"""

import sys
import yaml

from eliot import to_file
from twisted.python.filepath import FilePath
from twisted.python.usage import Options, UsageError

from flocker.common.runner import run_ssh
from flocker.common import gather_deferreds

to_file(sys.stdout)


class ClusterCommandOptions(Options):
    optParameters = [
        ['config-file', None, FilePath(u"managed.yaml"),
         'The path to an acceptance style configuration file.', FilePath],
        ['username', None, u"root",
         'The username to log in with.', unicode],
    ]

    def parseArgs(self, *command):
        self["command"] = command


def cluster_command_main(reactor, args, top_level, base_path):
    options = ClusterCommandOptions()
    try:
        options.parseOptions(args)
    except UsageError as e:
        sys.stderr.write("%s: %s\n" % (base_path.basename(), e))
        raise SystemExit(1)

    with options["config-file"].open() as f:
        config = yaml.load(f)

    return gather_deferreds(
        run_ssh(
            reactor=reactor,
            username=options["username"],
            host=address_pair[1],
            command=options["command"],
        )
        for address_pair in config['managed']['addresses']
    )
