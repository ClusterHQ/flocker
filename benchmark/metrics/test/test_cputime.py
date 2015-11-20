import subprocess
from uuid import uuid4

from ipaddr import IPAddress

from twisted.internet.task import Clock
from twisted.internet.threads import deferToThread
from twisted.trial.unittest import SynchronousTestCase, TestCase

from benchmark.metrics.cputime import (
    CPUTime, _CPUParser, get_node_cpu_times, _compute_change, SSHRunner,
)

from flocker.apiclient._client import FakeFlockerClient, Node


class CPUParseTests(SynchronousTestCase):

    def test_blank_line(self):
        """
        Blank lines ignored.
        """
        parser = _CPUParser()
        parser.lineReceived('')
        self.assertEqual(parser.result, {})

    def test_nodays(self):
        """
        CPU time line with no days parses correctly.
        """
        parser = _CPUParser()
        parser.lineReceived('proc  12:34:56')
        expected_cputime = (12 * 60 + 34) * 60 + 56
        self.assertEqual(parser.result, {'proc': expected_cputime})

    def test_days(self):
        """
        CPU time line with days parses correctly.
        """
        parser = _CPUParser()
        parser.lineReceived('proc  5-12:34:56')
        expected_cputime = ((5 * 24 + 12) * 60 + 34) * 60 + 56
        self.assertEqual(parser.result, {'proc': expected_cputime})

    def test_unexpected_line(self):
        """
        Line that doesn't fit expected pattern raises exception.
        """
        parser = _CPUParser()
        with self.assertRaises(ValueError) as e:
            parser.lineReceived('Unexpected Error Message')
        self.assertEqual(e.exception.args[-1], 'Unexpected Error Message')

    def test_unexpected_parse(self):
        """
        Line that has incorrect time raises exception.
        """
        parser = _CPUParser()
        with self.assertRaises(ValueError) as e:
            parser.lineReceived('proc 20:34')
        self.assertEqual(e.exception.args[-1], 'proc 20:34')


class _LocalRunner:

    def _run(self, command_args, handle_stdout):
        output = subprocess.check_output(command_args)
        for line in output.split('\n'):
            handle_stdout(line)

    def run(self, node, command_args, handle_stdout):
        # Ignore the `node` parameter, we just run locally.
        return deferToThread(self._run, command_args, handle_stdout)


class GetNodeCPUTimeTests(TestCase):

    def test_get_node_cpu_times(self):
        d = get_node_cpu_times(
            _LocalRunner(),
            Node(uuid=uuid4(), public_address=IPAddress('10.0.0.1')),
            ['init'],
        )

        def check(result):
            self.assertEqual(result.keys(), ['init'])

        d.addCallback(check)

        return d

    def test_no_such_process(self):
        """
        Errors result in output of None
        """
        d = get_node_cpu_times(
            _LocalRunner(),
            Node(uuid=uuid4(), public_address=IPAddress('10.0.0.1')),
            ['n0n-exist'],
        )

        def check(result):
            self.assertIs(result, None)

        d.addCallback(check)

        return d


class ComputeChangesTests(SynchronousTestCase):

    def test_compute_change(self):
        """
        Process measurements are handled correctly.
        """
        labels = ['node1', 'node2']
        before = [{'foo': 3, 'bar': 5}, {'foo': 10, 'bar': 2}]
        after = [{'foo': 4, 'bar': 5}, {'foo': 12, 'bar': 5}]
        result = _compute_change(labels, before, after)
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
        result = _compute_change(labels, before, after)
        self.assertEqual(result, {'node1': {'foo': 55}})

    def test_compute_change_lost_proc(self):
        """
        Process that only appears in ``before`` is ignored.
        """
        labels = ['node1']
        before = [{'foo': 555, 'bar': 5}]
        after = [{'foo': 600}]
        result = _compute_change(labels, before, after)
        self.assertEqual(result, {'node1': {'foo': 45}})

    def test_compute_change_error_before(self):
        """
        Error in before results in None result.
        """
        labels = ['node1']
        before = [None]
        after = [{'foo': 555, 'bar': 5}]
        result = _compute_change(labels, before, after)
        self.assertEqual(result, {'node1': None})

    def test_compute_change_error_after(self):
        """
        Error in after results in None result.
        """
        labels = ['node1']
        before = [{'foo': 555, 'bar': 5}]
        after = [None]
        result = _compute_change(labels, before, after)
        self.assertEqual(result, {'node1': None})


class CPUTimeTests(TestCase):

    def test_cpu_time(self):
        node1 = Node(uuid=uuid4(), public_address=IPAddress('10.0.0.1'))
        node2 = Node(uuid=uuid4(), public_address=IPAddress('10.0.0.2'))
        metric = CPUTime(
            Clock(), FakeFlockerClient([node1, node2]),
            _LocalRunner(), processes=['init'])
        d = metric.measure(lambda: 1)

        # Although it is unlikely, it's possible that we could get a CPU
        # time != 0, so filter values out.
        def filter(node_cpu_times):
            for process_times in node_cpu_times.values():
                if process_times:
                    for process in process_times:
                        process_times[process] = 0
            return node_cpu_times
        d.addCallback(filter)

        def check(result):
            self.assertEqual(
                result, {'10.0.0.1': {'init': 0}, '10.0.0.2': {'init': 0}})
        d.addCallback(check)
        return d
