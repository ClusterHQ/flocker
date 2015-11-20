# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
CPU time metric for the control service benchmarks.
"""

from zope.interface import implementer

from twisted.protocols.basic import LineOnlyReceiver

import eliot

from flocker.common import gather_deferreds
from flocker.common.runner import run_ssh

from benchmark._interfaces import IMetric

_FLOCKER_PROCESSES = {
    u'flocker-control',
    u'flocker-dataset-agent',
    u'flocker-container-agent',
    u'flocker-docker-plugin',
}


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


class CPUParser(LineOnlyReceiver):
    """
    Handler for the output lines returned from the cpu time command.
    """

    def __init__(self):
        self.result = {}

    def lineReceived(self, line):
        """
        Handle a single line output from the cpu time command.
        """
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
    """
    Run a command using ssh.

    :ivar reactor: Twisted Reactor.
    :ivar user: Remote user name.
    """

    def __init__(self, reactor, user=b'root'):
        self.reactor = reactor
        self.user = user

    def run(self, node, command_args, handle_stdout):
        """
        Run a command using SSH.

        :param Node node: Node to run command on.
        :param [str] command_args: List of command line arguments.
        :param callable handle_stdout: Function to handle each line of output.
        :return: Deferred, firing when complete.
        """
        d = run_ssh(
            self.reactor,
            self.user,
            node.public_address.exploded,
            command_args,
            handle_stdout=handle_stdout,
        )
        return d


def get_node_cpu_times(runner, node, processes):
    """
    Get the CPU times for processes running on a node.

    :param runner: A method of running a command on a node.
    :param node: A node to run the command on.
    :param processes: An iterator of process names to monitor.
    :return: Deferred firing with a dictionary mapping process names to
        elapsed cpu time.  If an error occurs, returns None (after
        logging error).
    """
    parser = CPUParser()
    d = runner.run(
        node,
        _GET_CPUTIME_COMMAND + [b",".join(processes)],
        handle_stdout=parser.lineReceived,
    )
    d.addCallback(lambda ignored: parser.result)
    d.addErrback(eliot.writeFailure)
    return d


def get_cluster_cpu_times(clock, runner, nodes, processes):
    """
    Get the CPU times for processes running on a cluster.

    :param clock: Twisted Reactor.
    :param runner: A method of running a command on a node.
    :param node: Node to run the command on.
    :param processes: An iterator of process names to monitor.
    :return: Deferred firing with a dictionary mapping process names to
        elapsed cpu time.  If an error occurs, returns None (after
        logging error).
    """
    return gather_deferreds(list(
        get_node_cpu_times(runner, node, processes)
        for node in nodes
    ))


def compute_change(labels, before, after):
    """
    Compute the difference between times retrieved ast different times.

    :param [str] labels: Label for each result.
    :param before: Times collected per process name for time 0.
    :param after: Times collected per process name for time 1.
    :return: Dictionary mapping labels to dictionaries mapping process
        names to elapsed CPU time between measurements.
    """
    result = {}
    for (label, before, after) in zip(labels, before, after):
        if before is None or after is None:
            value = None
        else:
            matched_keys = set(before) & set(after)
            value = {key: after[key] - before[key] for key in matched_keys}
        result[label] = value
    return result


@implementer(IMetric)
class CPUTime(object):
    """
    Measure the elapsed CPU time during an operation.
    """

    def __init__(
        self, clock, control_service, runner=None,
        processes=_FLOCKER_PROCESSES
    ):
        self.clock = clock
        self.control_service = control_service
        if runner is None:
            self.runner = SSHRunner(clock)
        else:
            self.runner = runner
        self.processes = processes

    def measure(self, f, *a, **kw):
        nodes = []
        before_cpu = []
        after_cpu = []

        # Retrieve the cluster nodes
        d = self.control_service.list_nodes().addCallback(nodes.extend)

        # Obtain elapsed CPU time before test
        d.addCallback(
            lambda _ignored: get_cluster_cpu_times(
                self.clock, self.runner, nodes, self.processes)
        ).addCallback(before_cpu.extend)

        # Perform the test function
        d.addCallback(lambda _ignored: f(*a, **kw))

        # Obtain elapsed CPU time after test
        d.addCallback(
            lambda _ignored: get_cluster_cpu_times(
                self.clock, self.runner, nodes, self.processes)
        ).addCallback(after_cpu.extend)

        # Create the result from before and after times
        d.addCallback(
            lambda _ignored: compute_change(
                (node.public_address.exploded for node in nodes),
                before_cpu, after_cpu
            )
        )

        return d
