# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
"""
Tests for ``admin.runner``.
"""

import os

from eliot.testing import capture_logging, assertHasMessage

from twisted.trial.unittest import TestCase
from twisted.python.failure import Failure
from twisted.internet.error import ProcessDone, ProcessTerminated

from flocker.testtools import (
    MemoryCoreReactor, FakeProcessReactor,
)

from ..runner import run, CommandProtocol, RUN_OUTPUT_MESSAGE


class ProcessCoreReactor(MemoryCoreReactor, FakeProcessReactor):
    """
    Fake IReactorCore and IReactorProcess implementation.
    """
    def __init__(self):
        MemoryCoreReactor.__init__(self)
        FakeProcessReactor.__init__(self)


class RunTests(TestCase):
    """
    Tests for ``run``.
    """
    def test_spawns_process(self):
        """
        Calling ``run`` spawns a process running the given command.
        """
        reactor = ProcessCoreReactor()
        run(reactor, ['command', 'and', 'args'])
        [process] = reactor.processes
        self.assertEqual(
            [process.executable,
             process.args,
             type(process.processProtocol)],
            ['command',
             ['command', 'and', 'args'],
             CommandProtocol])

    @capture_logging(
        assertHasMessage, RUN_OUTPUT_MESSAGE, {'line': 'hello:test_runner.py'})
    def test_writes_output(self, logger):
        """
        Output of the spawned process is written to standard output.
        """
        reactor = ProcessCoreReactor()
        run(reactor, ['command', 'and', 'args'])
        [process] = reactor.processes
        process.processProtocol.childDataReceived(1, "hello:test_runner.py\n")

    def test_registers_killer(self):
        """
        Calling ``run`` registers a before-shutdown event to kill the
        process.
        """
        reactor = ProcessCoreReactor()
        run(reactor, ['command', 'and', 'args'])
        [process] = reactor.processes

        self.assertEqual(
            reactor._triggers['shutdown'].before,
            [(process.transport.signalProcess, ('TERM',), {})])

    def test_unregisters_killer_success(self):
        """
        When the process ends succesfully, the before-shutdown event is
        unregistered.
        """
        reactor = ProcessCoreReactor()
        run(reactor, ['command', 'and', 'args'])
        [process] = reactor.processes

        process.processProtocol.processEnded(Failure(ProcessDone(0)))
        self.assertEqual(
            reactor._triggers['shutdown'].before,
            [])

    def test_unregisters_killer_failure(self):
        """
        When the process fails, the before-shutdown event is unregistered.
        """
        reactor = ProcessCoreReactor()
        d = run(reactor, ['command', 'and', 'args'])
        [process] = reactor.processes

        process.processProtocol.processEnded(Failure(ProcessTerminated(1)))
        self.failureResultOf(d)

        self.assertEqual(
            reactor._triggers['shutdown'].before,
            [])

    def test_process_success(self):
        """
        If the process ends with a success, the returned deferred fires with
        a succesful result.
        """

        reactor = ProcessCoreReactor()
        d = run(reactor, ['command', 'and', 'args'])
        [process] = reactor.processes

        expected_failure = Failure(ProcessDone(0))
        process.processProtocol.processEnded(expected_failure)
        self.successResultOf(d)

    def test_process_failure(self):
        """
        If the process ends with a failure, the returned deferred fires with
        the reason.
        """

        reactor = ProcessCoreReactor()
        d = run(reactor, ['command', 'and', 'args'])
        [process] = reactor.processes

        expected_failure = Failure(ProcessTerminated(1))
        process.processProtocol.processEnded(expected_failure)
        self.assertEqual(
            self.failureResultOf(d),
            expected_failure)

    def test_environment_default(self):
        """
        If no environment is provided, the current environment is used.
        """
        reactor = ProcessCoreReactor()
        run(reactor, ['command', 'and', 'args'])
        [process] = reactor.processes
        self.assertEqual(
            process.env,
            os.environ)

    def test_environment_given(self):
        """
        If an environment is provided, that environment is used.
        """
        expected_env = {'a': 'variable'}
        reactor = ProcessCoreReactor()
        run(reactor, ['command', 'and', 'args'], env=expected_env)
        [process] = reactor.processes
        self.assertEqual(
            process.env,
            expected_env)

    def test_working_directory(self):
        """
        If a working directory is specified, that directory is used.
        """
        expected_path = '/working/directory'
        reactor = ProcessCoreReactor()
        run(reactor, ['command', 'and', 'args'], path=expected_path)
        [process] = reactor.processes
        self.assertEqual(
            process.path,
            expected_path)

    def test_process_shutdown(self):
        """
        When the reactor is shutdown, the process is killed with signal `TERM`.
        """

        reactor = ProcessCoreReactor()
        run(reactor, ['command', 'and', 'args'])
        [process] = reactor.processes

        reactor.fireSystemEvent('shutdown')
        self.assertEqual(
            process.transport.signals,
            ['TERM'])

    def test_process_shutdown_unregister(self):
        """
        If the process is killed after shutting down, an error
        isn't raised.

        In particular, removing the killer doesn't cause an error.
        """

        reactor = ProcessCoreReactor()
        run(reactor, ['command', 'and', 'args'])
        [process] = reactor.processes

        reactor.fireSystemEvent('shutdown')
        process.processProtocol.processEnded(Failure(ProcessDone(0)))
