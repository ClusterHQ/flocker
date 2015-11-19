# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
CPU time metric for the control service benchmarks.
"""

from characteristic import Attribute, attributes
from pyrsistent import PClass, field, pset
from zope.interface import implementer

from twisted.protocols.basic import LineOnlyReceiver

from flocker.common import gather_deferreds
from flocker.common.runner import run_ssh

from .._interfaces import IMetric

_FLOCKER_PROCESSES = _JOURNAL_UNITS = pset({
    u'flocker-control',
    u'flocker-dataset-agent',
    u'flocker-container-agent',
})


_GET_CPUTIME_COMMAND = [
    # Use system ps to collect the information
    b'ps',
    # Output the command name (truncated) and the cputime of the process.
    # `=` provides a header.  Making all the headers blank prevents the header
    # line from being written.
    b'-o',
    b'comm=,cputime=',
    # Output lines for processes with names matching the following (values
    # supplied by invoker)
    b'-C',
]


class _CPUParser(LineOnlyReceiver):

    def __init__(self):
        self.result = {}

    def lineReceived(self, line):
        # Lines are like:
        #
        # flocker-control 1-00:03:41
        # flocker-dataset 00:18:14
        # flocker-contain 01:47:02
        if not line.strip():
            # ignore blank lines
            return
        try:
            name, formatted_cputime = line.split()
            parts = formatted_cputime.split(b'-', 1)
            # The last item is always HH:MM:SS. Split it and convert to
            # integers.
            h, m, s = [int(t) for t in parts.pop().split(b':')]
            # Anything left is the number of days
            days = int(parts[0]) if parts else 0
            cputime = ((days * 24 + h) * 60 + m) * 60 + s
        except ValueError as e:
            e.args = e.args + (line,)
            raise e

        self.result[name] = self.result.get(name, 0) + cputime


class SSHRunner:

    def __init__(self, reactor, node, user=b'root'):
        self.reactor = reactor
        self.node = node
        self.user = user

    def run(self, command_args, handle_stdout):
        d = run_ssh(
            self.reactor,
            self.user,
            self.node.public_address.exploded,
            command_args,
            handle_stdout=handle_stdout,
        )
        return d


def get_node_cpu_times(runner, processes):
    parser = _CPUParser()
    d = runner.run(
        _GET_CPUTIME_COMMAND + [b",".join(processes)],
        handle_stdout=parser.lineReceived,
    )
    d.addCallback(lambda ignored: parser.result)
    return d


def _get_cluster_cpu_times(clock, nodes, processes):
    return gather_deferreds(list(
        get_node_cpu_times(SSHRunner(clock, node), processes)
        for node in nodes
    ))


def _compute_change(labels, before, after):
    result = {}
    for (label, before, after) in zip(labels, before, after):
        matched_keys = set(before) & set(after)
        value = {key: after[key] - before[key] for key in matched_keys}
        result[label] = value
    return result


@implementer(IMetric)
class CPUTime(PClass):
    """
    Measure the elapsed CPU time during an operation.
    """
    clock = field(mandatory=True)
    control_service = field(mandatory=True)

    def measure(self, f, *a, **kw):
        nodes = []
        before_cpu = []
        after_cpu = []

        # Retrieve the cluster nodes
        d = self.control_service.list_nodes().addCallback(nodes.extend)

        # Obtain elapsed CPU time before test
        d.addCallback(
            lambda _ignored: _get_cluster_cpu_times(
                self.clock, nodes, _FLOCKER_PROCESSES)
        ).addCallback(before_cpu.extend)

        # Perform the test function
        d.addCallback(lambda _ignored: f(*a, **kw))

        # Obtain elapsed CPU time after test
        d.addCallback(
            lambda _ignored: _get_cluster_cpu_times(
                self.clock, nodes, _FLOCKER_PROCESSES)
        ).addCallback(after_cpu.extend)

        # Create the result from before and after times
        d.addCallback(
            lambda _ignored: _compute_change(
                (node.public_address.exploded for node in nodes),
                before_cpu, after_cpu
            )
        )

        return d
