import subprocess

from twisted.internet.threads import deferToThread
from twisted.trial.unittest import SynchronousTestCase, TestCase

from benchmark.metrics.cputime import (
    _CPUParser, get_node_cpu_times, _compute_change
)


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

    def run(self, command_args, handle_stdout):
        return deferToThread(self._run, command_args, handle_stdout)


class GetNodeCPUTimeTests(TestCase):

    def test_get_node_cpu_times(self):
        d = get_node_cpu_times(_LocalRunner(), ['init'])

        def check(result):
            self.assertEqual(result.keys(), ['init'])

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


class CPUTimeTests(TestCase):

    # XXX
    pass
