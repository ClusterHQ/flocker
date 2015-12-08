# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
CPU time metric for the control service benchmarks.
"""

from zope.interface import implementer

from twisted.protocols.basic import LineOnlyReceiver

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

# A string that not a valid process name.  Any name with a space is good
# because metric does not support process names containing spaces.
WALLCLOCK_LABEL = '-- WALL --'


class CPUParser(LineOnlyReceiver):
    """
    Handler for the output lines returned from the cpu time command.

    After parsing, the ``result`` attribute will contain a dictionary
    mapping process names to elapsed CPU time.  Process names may be
    truncated.  A special process will be added indicating the wallclock
    time.
    """

    def __init__(self, reactor):
        self._reactor = reactor
        self.result = {}

    def lineReceived(self, line):
        """
        Handle a single line output from the cpu time command.
        """
        # Add wallclock time when receiving first line of output.
        if WALLCLOCK_LABEL not in self.result:
            self.result[WALLCLOCK_LABEL] = self._reactor.seconds()

        # Lines are like:
        #
        # flocker-control 1-00:03:41
        # flocker-dataset 00:18:14
        # flocker-contain 01:47:02
        # ps <defunct>    00:00:02
        if not line.strip():
            # ignore blank lines
            return
        try:
            # Process names may contain spaces, and may end with <defunct>, so
            # split off leftmost and rightmost words.  We specify that process
            # names must not contains spaces, so that this works.
            words = line.split()
            name = words[0]
            formatted_cputime = words[-1]
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


class SSHRunner(object):
    """
    Run a command using ssh.

    :ivar reactor: Twisted Reactor.
    :ivar cluster: Benchmark cluster.
    :ivar user: Remote user name.
    """

    def __init__(self, reactor, cluster, user=b'root'):
        self.reactor = reactor
        self.cluster = cluster
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
            self.cluster.public_address(node.public_address).exploded,
            command_args,
            handle_stdout=handle_stdout,
        )
        return d


def get_node_cpu_times(reactor, runner, node, processes):
    """
    Get the CPU times for processes running on a node.

    :param reactor: Twisted Reactor.
    :param runner: A method of running a command on a node.
    :param node: A node to run the command on.
    :param processes: An iterator of process names to monitor. The process
        names must not contain spaces.
    :return: Deferred firing with a dictionary mapping process names to
        elapsed cpu time.  Process names may be truncated in the dictionary.
        If an error occurs, returns None (after logging error).
    """
    # If no named processes are running, `ps` will return an error.  To
    # distinguish this case from real errors, ensure that at least one process
    # is present by adding `ps` as a monitored process.  Remove it later.
    parser = CPUParser(reactor)
    d = runner.run(
        node,
        _GET_CPUTIME_COMMAND + [b','.join(processes) + b',ps'],
        handle_stdout=parser.lineReceived,
    )

    def get_parser_result(ignored):
        result = parser.result
        # Remove unwanted ps values.
        del result['ps']
        return result
    d.addCallback(get_parser_result)

    return d


def get_cluster_cpu_times(reactor, runner, nodes, processes):
    """
    Get the CPU times for processes running on a cluster.

    :param reactor: Twisted Reactor.
    :param runner: A method of running a command on a node.
    :param node: Node to run the command on.
    :param processes: An iterator of process names to monitor. The process
        names must not contain spaces.
    :return: Deferred firing with a dictionary mapping process names to
        elapsed cpu time.  Process names may be truncated in the dictionary.
        If an error occurs, returns None (after logging error).
    """
    return gather_deferreds(list(
        get_node_cpu_times(reactor, runner, node, processes)
        for node in nodes
    ))


def compute_change(labels, before, after):
    """
     Compute the difference between CPU times from consecutive measurements.

    :param [str] labels: Label for each result.
    :param before: Times collected per process name for time 0.
    :param after: Times collected per process name for time 1.
    :return: Dictionary mapping labels to dictionaries mapping process
        names to elapsed CPU time between measurements.
    """
    result = {}
    for (label, before, after) in zip(labels, before, after):
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
        self, reactor, cluster, runner=None, processes=_FLOCKER_PROCESSES
    ):
        self.reactor = reactor
        self.cluster = cluster
        if runner is None:
            self.runner = SSHRunner(reactor, cluster)
        else:
            self.runner = runner
        self.processes = processes

    def measure(self, f, *a, **kw):
        nodes = []
        before_cpu = []
        after_cpu = []

        control_service = self.cluster.get_control_service(self.reactor)

        # Retrieve the cluster nodes
        d = control_service.list_nodes().addCallback(nodes.extend)

        # Obtain elapsed CPU time before test
        d.addCallback(
            lambda _ignored: get_cluster_cpu_times(
                self.reactor, self.runner, nodes, self.processes)
        ).addCallback(before_cpu.extend)

        # Perform the test function
        d.addCallback(lambda _ignored: f(*a, **kw))

        # Obtain elapsed CPU time after test
        d.addCallback(
            lambda _ignored: get_cluster_cpu_times(
                self.reactor, self.runner, nodes, self.processes)
        ).addCallback(after_cpu.extend)

        # Create the result from before and after times
        d.addCallback(
            lambda _ignored: compute_change(
                (node.public_address.exploded for node in nodes),
                before_cpu, after_cpu
            )
        )

        return d
