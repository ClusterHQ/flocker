# Copyright 2015 ClusterHQ Inc.  See LICENSE file for details.
"""
CPU time metric for the control service benchmarks.
"""

from os import environ

from zope.interface import implementer

from twisted.protocols.basic import LineOnlyReceiver

from flocker.common import gather_deferreds
from flocker.common.runner import run_ssh

from benchmark._interfaces import IMetric

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

_GET_INIT_PROCESS_NAME_COMMAND = [
    # Use system ps to collect the information
    b'ps',
    # Output the command name (truncated)
    # `=` provides a header.  Making the header blank prevents the header
    # line from being written.
    b'-o', b'comm=',
    # Output line for process 1
    b'-p', b'1',
]

_FLOCKER_PROCESSES = {
    u'flocker-control',
    u'flocker-dataset-agent',
    u'flocker-container-agent',
    u'flocker-docker-plugin',
}

# A string that not a valid process name.  Any name with a space is good
# because metric does not support process names containing spaces.
WALLCLOCK_LABEL = '-- WALL --'


class ProcessNameParser(LineOnlyReceiver):
    """
    Handler for the output lines returned from the cpu time command.

    After parsing, the ``result`` attribute will contain a dictionary
    mapping process names to elapsed CPU time.  Process names may be
    truncated.  A special process will be added indicating the wallclock
    time.
    """

    def __init__(self):
        self.result = ''

    def lineReceived(self, line):
        """
        Handle a single line output from the cpu time command.
        """
        if line:
            self.result = line.strip()


def get_node_init_process_name(runner, node):
    """
    Get the name of process 1 on a node.

    :param runner: A method of running a command on a node.
    :param node: A node to run the command on.
    :return: Deferred firing with the name of process 1 on the node.
    """
    parser = ProcessNameParser()
    d = runner.run(
        node,
        _GET_INIT_PROCESS_NAME_COMMAND,
        handle_stdout=parser.lineReceived,
    )

    d.addCallback(lambda _ignored: parser.result)

    return d


def get_cluster_init_process_names(runner, nodes):
    """
    Get the names of process 1 running on each node.

    :param runner: A method of running a command on a node.
    :param nodes: A list of Node to run the command on.
    :return: Deferred firing with a list of process names.
    """
    return gather_deferreds(list(
        get_node_init_process_name(runner, node)
        for node in nodes
    ))


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


def get_node_cpu_times(reactor, runner, node, known_name, processes):
    """
    Get the CPU times for processes running on a node.

    :param reactor: Twisted Reactor.
    :param runner: A method of running a command on a node.
    :param node: A node to run the command on.
    :param known_name: The name of a process which is known to be running on
        the node.
    :param processes: An iterator of process names to monitor. The process
        names must not contain spaces.
    :return: Deferred firing with a dictionary mapping process names to
        elapsed cpu time.  Process names may be truncated in the dictionary.
        If an error occurs, returns None (after logging error).
    """
    # If no named processes are running, `ps` will return an error.  To
    # distinguish this case from real errors, ensure that at least one
    # process is present by adding an always present process (pid 1) as
    # a monitored process.  Remove it later.
    process_list = list(processes)
    if known_name in processes:
        delete_known_name = False
    else:
        process_list.append(known_name)
        delete_known_name = True

    parser = CPUParser(reactor)
    d = runner.run(
        node,
        _GET_CPUTIME_COMMAND + [b','.join(process_list)],
        handle_stdout=parser.lineReceived,
    )

    def get_parser_result(ignored):
        result = parser.result
        # Remove unwanted value.
        if delete_known_name and known_name in result:
            del result[known_name]
        return result
    d.addCallback(get_parser_result)

    return d


def get_cluster_cpu_times(reactor, runner, nodes, inits, processes):
    """
    Get the CPU times for processes running on a cluster.

    :param reactor: Twisted Reactor.
    :param runner: A method of running a command on a node.
    :param nodes: A list of nodes to run the command on.
    :param inits: The names of the init process on each node.
    :param processes: An iterator of process names to monitor. The process
        names must not contain spaces.
    :return: Deferred firing with a dictionary mapping process names to
        elapsed cpu time.  Process names may be truncated in the dictionary.
        If an error occurs, returns None (after logging error).
    """
    return gather_deferreds(list(
        get_node_cpu_times(reactor, runner, node, init, processes)
        for node, init in zip(nodes, inits)
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


class SSHRunner(object):
    """
    Run a command using ssh.

    :ivar reactor: Twisted Reactor.
    :ivar cluster: Benchmark cluster.
    :ivar user: Remote user name.
    """

    def __init__(self, reactor, cluster, user=b'root', config_file=None):
        self.reactor = reactor
        self.cluster = cluster
        self.user = user
        self.config_file = config_file

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
            self.config_file,
            handle_stdout=handle_stdout,
        )
        return d


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
            self.runner = SSHRunner(
                reactor, cluster, config_file=environ.get('BENCHMARK_SSH_CONFIG', None)
            )
        else:
            self.runner = runner
        self.processes = processes

    def measure(self, f, *a, **kw):
        nodes = []
        inits = []
        before_cpu = []
        after_cpu = []

        control_service = self.cluster.get_control_service(self.reactor)

        # Retrieve the cluster nodes
        d = control_service.list_nodes().addCallback(nodes.extend)

        # Obtain the init process on each node - these are required because
        # we need to ensure that we name at least one process that exists.
        d.addCallback(
            lambda _ignored: get_cluster_init_process_names(self.runner, nodes)
        ).addCallback(inits.extend)

        # Obtain elapsed CPU time before test
        d.addCallback(
            lambda _ignored: get_cluster_cpu_times(
                self.reactor, self.runner, nodes, inits, self.processes)
        ).addCallback(before_cpu.extend)

        # Perform the test function
        d.addCallback(lambda _ignored: f(*a, **kw))

        # Obtain elapsed CPU time after test
        d.addCallback(
            lambda _ignored: get_cluster_cpu_times(
                self.reactor, self.runner, nodes, inits, self.processes)
        ).addCallback(after_cpu.extend)

        # Create the result from before and after times
        d.addCallback(
            lambda _ignored: compute_change(
                (node.public_address.exploded for node in nodes),
                before_cpu, after_cpu
            )
        )

        return d
