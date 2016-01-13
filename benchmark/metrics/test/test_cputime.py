import platform
import subprocess
from unittest import skipIf
from uuid import uuid4

from ipaddr import IPAddress
from zope.interface.verify import verifyClass

from twisted.internet.task import Clock
from twisted.internet.threads import deferToThread

from flocker.apiclient import FakeFlockerClient, Node
from flocker.testtools import TestCase, AsyncTestCase

from benchmark.cluster import BenchmarkCluster
from benchmark._interfaces import IMetric
from benchmark.metrics.cputime import (
    WALLCLOCK_LABEL, CPUTime, CPUParser, get_node_cpu_times, compute_change,
)

# Process 1 (usually `init`, `systemd`, or `launchd`) provides a process
# name that is always present.
_standard_process = subprocess.check_output(
    ['ps', '-p', '1', '-o', 'comm=']
).strip()

# The command used to check cputimes only works on Linux
on_linux = skipIf(platform.system() != 'Linux', 'Requires Linux')


class CPUParseTests(TestCase):
    """
    Test parsing of CPU time command.
    """

    def test_blank_line(self):
        """
        Blank lines are ignored.
        """
        parser = CPUParser(Clock())
        parser.lineReceived('')
        self.assertEqual(parser.result, {WALLCLOCK_LABEL: 0})

    def test_nodays(self):
        """
        CPU time line with no days part parses correctly.
        """
        parser = CPUParser(Clock())
        parser.lineReceived('proc  12:34:56')
        expected_cputime = (12 * 60 + 34) * 60 + 56
        self.assertEqual(
            parser.result, {'proc': expected_cputime, WALLCLOCK_LABEL: 0}
        )

    def test_days(self):
        """
        CPU time line with a days part parses correctly.
        """
        parser = CPUParser(Clock())
        parser.lineReceived('proc  5-12:34:56')
        expected_cputime = ((5 * 24 + 12) * 60 + 34) * 60 + 56
        self.assertEqual(
            parser.result, {'proc': expected_cputime, WALLCLOCK_LABEL: 0}
        )

    def test_unexpected_line(self):
        """
        Line that doesn't fit expected pattern raises exception.
        """
        parser = CPUParser(Clock())
        exception = self.assertRaises(
            ValueError,
            parser.lineReceived,
            'Unexpected Error Message'
        )
        self.assertEqual(exception.args[-1], 'Unexpected Error Message')

    def test_unexpected_parse(self):
        """
        Line that has incorrectly formatted time raises exception.
        """
        parser = CPUParser(Clock())
        exception = self.assertRaises(
            ValueError,
            parser.lineReceived,
            'proc 20:34'
        )
        self.assertEqual(exception.args[-1], 'proc 20:34')


class _LocalRunner(object):
    """
    Like SSHRunner, but runs command locally.
    """

    def _run(self, command_args, handle_stdout):
        output = subprocess.check_output(command_args)
        for line in output.split('\n'):
            handle_stdout(line)

    def run(self, node, command_args, handle_stdout):
        # Ignore the `node` parameter, we just run locally.
        return deferToThread(self._run, command_args, handle_stdout)


class GetNodeCPUTimeTests(AsyncTestCase):
    """
    Test ``get_node_cpu_times`` command.
    """

    @on_linux
    def test_get_node_cpu_times(self):
        """
        Success results in output of dictionary containing process names.
        """
        d = get_node_cpu_times(
            Clock(),
            _LocalRunner(),
            Node(uuid=uuid4(), public_address=IPAddress('10.0.0.1')),
            [_standard_process],
        )

        def check(result):
            self.assertEqual(
                result.keys(), [_standard_process, WALLCLOCK_LABEL]
            )

        d.addCallback(check)

        return d

    @on_linux
    def test_no_such_process(self):
        """
        If processes do not exist, only wallclock time is returned.
        """
        d = get_node_cpu_times(
            Clock(),
            _LocalRunner(),
            Node(uuid=uuid4(), public_address=IPAddress('10.0.0.1')),
            ['n0n-exist'],
        )

        d.addCallback(self.assertEqual, {WALLCLOCK_LABEL: 0.0})

        return d


class ComputeChangesTests(TestCase):
    """
    Test computation of CPU time change between two measurements.
    """

    def test_compute_change(self):
        """
        Process measurements are handled correctly.
        """
        labels = ['node1', 'node2']
        before = [{'foo': 3, 'bar': 5}, {'foo': 10, 'bar': 2}]
        after = [{'foo': 4, 'bar': 5}, {'foo': 12, 'bar': 5}]
        result = compute_change(labels, before, after)
        self.assertEqual(result, {
            'node1': {'foo': 1, 'bar': 0},
            'node2': {'foo': 2, 'bar': 3},
            })

    def test_compute_change_new_proc(self):
        """
        Process that only appears in ``after`` is ignored.
        """
        labels = ['node1']
        before = [{'foo': 500}]
        after = [{'foo': 555, 'bar': 5}]
        result = compute_change(labels, before, after)
        self.assertNotIn('bar', result['node1'])

    def test_compute_change_lost_proc(self):
        """
        Process that only appears in ``before`` is ignored.
        """
        labels = ['node1']
        before = [{'foo': 555, 'bar': 5}]
        after = [{'foo': 600}]
        result = compute_change(labels, before, after)
        self.assertNotIn('bar', result['node1'])


class CPUTimeTests(AsyncTestCase):
    """
    Test top-level CPU time metric.
    """

    def test_implements_IMetric(self):
        """
        CPUTime provides the IMetric interface.
        """
        verifyClass(IMetric, CPUTime)

    @on_linux
    def test_cpu_time(self):
        """
        Fake Flocker cluster gives expected results.
        """
        clock = Clock()
        node1 = Node(uuid=uuid4(), public_address=IPAddress('10.0.0.1'))
        node2 = Node(uuid=uuid4(), public_address=IPAddress('10.0.0.2'))
        metric = CPUTime(
            clock,
            BenchmarkCluster(
                IPAddress('10.0.0.1'),
                lambda reactor: FakeFlockerClient([node1, node2]),
                {},
                None,
            ),
            _LocalRunner(),
            processes=[_standard_process]
        )
        d = metric.measure(lambda: clock.advance(5))

        # Although it is unlikely, it's possible that we could get a CPU
        # time != 0, so filter values out.
        def filter(node_cpu_times):
            for process_times in node_cpu_times.values():
                if process_times:
                    for process in process_times:
                        if process != WALLCLOCK_LABEL:
                            process_times[process] = 0
            return node_cpu_times
        d.addCallback(filter)

        def check(result):
            self.assertEqual(
                result,
                {
                    '10.0.0.1': {_standard_process: 0, WALLCLOCK_LABEL: 5},
                    '10.0.0.2': {_standard_process: 0, WALLCLOCK_LABEL: 5}
                }
            )
        d.addCallback(check)
        return d
