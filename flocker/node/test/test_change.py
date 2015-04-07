# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.node._change``.
"""

from twisted.trial.unittest import SynchronousTestCase
from twisted.internet.defer import FirstError, Deferred, succeed, fail

from ..testtools import ControllableAction, ControllableDeployer

from .. import sequentially, in_parallel, run_state_change

from .istatechange import make_istatechange_tests

DEPLOYER = ControllableDeployer(u"192.168.1.1", (), ())


SequentiallyIStateChangeTests = make_istatechange_tests(
    sequentially, dict(changes=[1]), dict(changes=[2]))
InParallelIStateChangeTests = make_istatechange_tests(
    in_parallel, dict(changes=[1]), dict(changes=[2]))


def _test_nested_change(case, outer_factory, inner_factory):
    """
    Assert that ``IChangeState`` providers wrapped inside ``inner_factory``
    wrapped inside ``outer_factory`` are run with the same deployer argument as
    is passed to ``run_state_change``.

    :param TestCase case: A running test.
    :param outer_factory: Either ``sequentially`` or ``in_parallel`` to
        construct the top-level change to pass to ``run_state_change``.
    :param inner_factory: Either ``sequentially`` or ``in_parallel`` to
        construct a change to include the top-level change passed to
        ``run_state_change``.

    :raise: A test failure if the inner change is not run with the same
        deployer as is passed to ``run_state_change``.
    """
    inner_action = ControllableAction(result=succeed(None))
    subchanges = [
        ControllableAction(result=succeed(None)),
        inner_factory(changes=[inner_action]),
        ControllableAction(result=succeed(None))
    ]
    change = outer_factory(changes=subchanges)
    run_state_change(change, DEPLOYER)
    case.assertEqual(
        (True, DEPLOYER),
        (inner_action.called, inner_action.deployer)
    )


class SequentiallyTests(SynchronousTestCase):
    """
    Tests for handling of ``sequentially`` by ``run_state_changes``.
    """
    def test_subchanges_get_deployer(self):
        """
        ``run_state_changes`` accepts the result of ``sequentially`` and runs
        each of its changes with the given deployer.
        """
        subchanges = [ControllableAction(result=succeed(None)),
                      ControllableAction(result=succeed(None))]
        change = sequentially(changes=subchanges)
        run_state_change(change, DEPLOYER)
        self.assertEqual(
            list(c.deployer for c in subchanges),
            [DEPLOYER, DEPLOYER]
        )

    def test_result(self):
        """
        When ``run_state_changes`` is called with the result of
        ``sequentially``, the returned ``Deferred`` fires when all of the
        changes passed to ``sequentially`` have completed.
        """
        not_done1 = Deferred()
        not_done2 = Deferred()
        subchanges = [ControllableAction(result=not_done1),
                      ControllableAction(result=not_done2)]
        change = sequentially(changes=subchanges)
        result = run_state_change(change, DEPLOYER)
        self.assertNoResult(result)
        not_done1.callback(None)
        self.assertNoResult(result)
        not_done2.callback(None)
        self.successResultOf(result)

    def test_in_order(self):
        """
        The changes passed to ``sequentially`` are run in order by
        ``run_state_changes``.
        """
        # We have two changes; the first one will not finish until we fire
        # not_done, the second one will finish as soon as its run() is
        # called.
        not_done = Deferred()
        subchanges = [ControllableAction(result=not_done),
                      ControllableAction(result=succeed(None))]
        change = sequentially(changes=subchanges)
        # Run the sequential change. We expect the first ControllableAction's
        # run() to be called, but we expect second one *not* to be called
        # yet, since first one has finished.
        run_state_change(change, DEPLOYER)
        called = [subchanges[0].called,
                  subchanges[1].called]
        not_done.callback(None)
        called.append(subchanges[1].called)
        self.assertEqual(called, [True, False, True])

    def test_failure_stops_later_change(self):
        """
        When called with the result of ``sequentially``, ``run_state_changes``
        stops after the first change that fails and does not run changes after
        that.
        """
        not_done = Deferred()
        subchanges = [ControllableAction(result=not_done),
                      ControllableAction(result=succeed(None))]
        change = sequentially(changes=subchanges)
        result = run_state_change(change, DEPLOYER)
        called = [subchanges[1].called]
        exception = RuntimeError()
        not_done.errback(exception)
        called.extend([subchanges[1].called,
                       self.failureResultOf(result).value])
        self.assertEqual(called, [False, False, exception])

    def test_nested_sequentially(self):
        """
        ``run_state_changes`` executes all of the changes in a ``sequentially``
        nested within another ``sequentially``.
        """
        _test_nested_change(self, sequentially, sequentially)

    def test_nested_in_parallel(self):
        """
        ``run_state_changes`` executes all of the changes in an ``in_parallel``
        nested within a ``sequentially``.
        """
        _test_nested_change(self, sequentially, in_parallel)


class InParallelTests(SynchronousTestCase):
    """
    Tests for handling of ``in_parallel`` by ``run_state_changes``.
    """
    def test_subchanges_get_deployer(self):
        """
        ``run_state_changes`` accepts the result of ``in_parallel`` and runs
        each of its changes with the given deployer.
        """
        subchanges = [ControllableAction(result=succeed(None)),
                      ControllableAction(result=succeed(None))]
        change = in_parallel(changes=subchanges)
        run_state_change(change, DEPLOYER)
        self.assertEqual([c.deployer for c in subchanges],
                         [DEPLOYER, DEPLOYER])

    def test_result(self):
        """
        When ``run_state_changes`` is called with the result of
        ``in_parallel``, the returned ``Deferred`` fires when all of the
        changes passed to ``sequentially`` have completed.
        """
        not_done1 = Deferred()
        not_done2 = Deferred()
        subchanges = [ControllableAction(result=not_done1),
                      ControllableAction(result=not_done2)]
        change = in_parallel(changes=subchanges)
        result = run_state_change(change, DEPLOYER)
        self.assertNoResult(result)
        not_done1.callback(None)
        self.assertNoResult(result)
        not_done2.callback(None)
        self.successResultOf(result)

    def test_in_parallel(self):
        """
        The changes passed to ``in_parallel`` are run in parallel (that is,
        they are all started before any of them completes) by
        ``run_state_changes``.
        """
        # The first change will not finish immediately when run(), but we
        # expect the second one to be run() nonetheless.
        subchanges = [ControllableAction(result=Deferred()),
                      ControllableAction(result=succeed(None))]
        change = in_parallel(changes=subchanges)
        run_state_change(change, DEPLOYER)
        called = [subchanges[0].called,
                  subchanges[1].called]
        self.assertEqual(called, [True, True])

    def test_failure_result(self):
        """
        When called with the result of ``in_parallel``, ``run_state_changes``
        returns a ``Deferred`` that fires with the failure which occurs first.
        """
        subchanges = [ControllableAction(result=fail(RuntimeError()))]
        change = in_parallel(changes=subchanges)
        result = run_state_change(change, DEPLOYER)
        failure = self.failureResultOf(result, FirstError)
        self.assertEqual(failure.value.subFailure.type, RuntimeError)
        self.flushLoggedErrors(RuntimeError)

    def test_failure_all_logged(self):
        """
        When multiple changes passed to ``in_parallel`` fail,
        ``run_state_changes`` logs those failures.
        """
        subchanges = [
            ControllableAction(result=fail(ZeroDivisionError('e1'))),
            ControllableAction(result=fail(ZeroDivisionError('e2'))),
            ControllableAction(result=fail(ZeroDivisionError('e3'))),
        ]
        change = in_parallel(changes=subchanges)
        result = run_state_change(change, DEPLOYER)
        self.failureResultOf(result, FirstError)

        self.assertEqual(
            len(subchanges),
            len(self.flushLoggedErrors(ZeroDivisionError))
        )

    def test_nested_in_parallel(self):
        """
        ``run_state_changes`` executes all of the changes in an ``in_parallel``
        nested within another ``in_parallel``.
        """
        _test_nested_change(self, in_parallel, in_parallel)

    def test_nested_sequentially(self):
        """
        ``run_state_changes`` executes all of the changes in a ``sequentially``
        nested within an ``in_parallel``.
        """
        _test_nested_change(self, in_parallel, sequentially)
