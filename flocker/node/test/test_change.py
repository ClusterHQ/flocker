# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for ``flocker.node._change``.
"""

from zope.interface import implementer

from pyrsistent import PRecord, field

from twisted.trial.unittest import SynchronousTestCase
from twisted.internet.defer import FirstError, Deferred, succeed, fail
from twisted.python.components import proxyForInterface

from eliot import ActionType
from eliot.testing import validate_logging, assertHasAction

from ..testtools import (
    CONTROLLABLE_ACTION_TYPE, ControllableAction, ControllableDeployer,
    DummyDeployer
)
from ...testtools import CustomException

from .. import IStateChange, sequentially, in_parallel, run_state_change

from .istatechange import (
    DummyStateChange, RunSpyStateChange, make_istatechange_tests,
)

DEPLOYER = ControllableDeployer(u"192.168.1.1", (), ())


def _superlative(interface, comparison_result):
    """
    Create a proxy type for ``interface`` which also overrides comparison to
    return a particular result.

    :param zope.interface.Interface interface: The interface for which to
        proxy.
    :param int comparison_result: A value to return from ``__cmp__`` as
        implemented on the proxy type.

    :return: The new proxy type.
    """
    class ComparisonProxy(proxyForInterface(interface, "_original")):
        def __cmp__(self, other):
            return comparison_result
    return ComparisonProxy


def smallest(interface, instance):
    """
    Create a proxy for an instance which makes it sort smaller than anything it
    is compared to.

    :param zope.interface.Interface interface: The interface to proxy.
    :param instance: Any object providing ``interface``.

    :return: An object providing ``interface`` and also comparing as smaller
        than anything else.
    """
    return _superlative(interface, -1)(instance)


def largest(interface, instance):
    """
    Create a proxy for an instance which makes it sort larger than anything it
    is compared to.

    :param zope.interface.Interface interface: The interface to proxy.
    :param instance: Any object providing ``interface``.

    :return: An object providing ``interface`` and also comparing as larger
        than anything else.
    """
    return _superlative(interface, 1)(instance)


@implementer(IStateChange)
class BrokenAction(PRecord):
    """
    An ``IStateChange`` implementation that synchronously raised an exception
    instead of returning a ``Deferred``.
    """
    exception = field(mandatory=True)

    @property
    def eliot_action(self):
        return ActionType(
            u"flocker:test:broken_action",
            [], [],
            u"An action used by tests for handling of broken IStateChange "
            u"implementations.",
        )()

    def run(self, deployer):
        raise self.exception


class DummyStateChangeIStateChangeTests(
        make_istatechange_tests(
            DummyStateChange, dict(value=1), dict(value=2)
        )
):
    """
    Tests for the ``DummyStateChange`` ``IStateChange`` implementation.
    """


class RunSpyStateChangeIStateChangeTests(
        make_istatechange_tests(
            RunSpyStateChange, dict(value=1), dict(value=2)
        )
):
    """
    Tests for the ``RunSpyStateChange`` ``IStateChange`` implementation.
    """


class SequentiallyIStateChangeTests(
        make_istatechange_tests(
            sequentially, dict(changes=[1]), dict(changes=[2])
        )
):
    """
    Tests for the ``IStateChange`` implementation provided by the object
    returned by ``sequentially``.
    """


class InParallelIStateChangeTests(
        make_istatechange_tests(
            in_parallel, dict(changes=[1]), dict(changes=[2])
        )
):
    """
    Tests for the ``IStateChange`` implementation provided by the object
    returned by ``in_parallel``.
    """
    def test_change_order_equality(self):
        """
        If the same changes are passed to ``in_parallel`` but in a different
        order, the resulting ``IStateChange`` providers still compare as equal
        to each other.
        """
        first_change = DummyStateChange(value=1)
        second_change = DummyStateChange(value=2)
        first_parallel = in_parallel(changes=[first_change, second_change])
        second_parallel = in_parallel(changes=[second_change, first_change])

        self.assertEqual(
            (True, False),
            (first_parallel == second_parallel,
             first_parallel != second_parallel)
        )

    def test_duplicates_run(self):
        """
        If the same change is passed to ``in_parallel`` twice then it is run
        twice.
        """
        deployer = DummyDeployer()
        the_change = RunSpyStateChange(value=0)
        parallel = in_parallel(changes=[the_change, the_change])
        self.successResultOf(parallel.run(deployer))
        self.assertEqual(2, the_change.value)


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

    def test_exception_result(self):
        """
        When called with the result of ``in_parallel``, ``run_state_changes``
        returns a ``Deferred`` that fires with the first exception raised
        (synchronously, not returned as a ``Failure``).
        """
        subchanges = [BrokenAction(exception=CustomException())]
        change = in_parallel(changes=subchanges)
        result = run_state_change(change, DEPLOYER)
        failure = self.failureResultOf(result, FirstError)
        self.assertEqual(failure.value.subFailure.type, CustomException)
        self.flushLoggedErrors(CustomException)

    def test_changes_run_after_exception(self):
        """
        If one of the ``IStateChange`` implementations passed to
        ``in_parallel`` raises an exception, ``run_state_changes`` nevertheless
        runs the other ``IStateChange`` implementations passed along with it.
        """
        some_change = ControllableAction(result=None)
        other_change = ControllableAction(result=None)
        subchanges = [
            smallest(IStateChange, some_change),
            BrokenAction(exception=CustomException()),
            largest(IStateChange, other_change),
        ]
        change = in_parallel(changes=subchanges)
        result = run_state_change(change, DEPLOYER)
        self.failureResultOf(result, FirstError)
        self.flushLoggedErrors(CustomException)
        self.assertEqual(
            (some_change.called, other_change.called),
            (True, True),
            "Other changes passed to in_parallel with a broken IStateChange "
            "were not run."
        )

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


class RunStateChangeTests(SynchronousTestCase):
    """
    Direct unit tests for ``run_state_change``.
    """
    def test_run(self):
        """
        ``run_state_change`` calls the ``run`` method of the ``IStateChange``
        passed to it and passes along the same deployer it was called with.
        """
        action = ControllableAction(result=succeed(None))
        run_state_change(action, DEPLOYER)
        self.assertTrue(
            (True, DEPLOYER),
            (action.called, action.deployer)
        )

    @validate_logging(
        assertHasAction, CONTROLLABLE_ACTION_TYPE, succeeded=True,
    )
    def test_succeed(self, logger):
        """
        If the change passed to ``run_state_change`` returns a ``Deferred``
        that succeeds, the ``Deferred`` returned by ``run_state_change``
        succeeds.
        """
        action = ControllableAction(result=succeed(None))
        action._logger = logger
        self.assertIs(
            None, self.successResultOf(run_state_change(action, DEPLOYER))
        )

    @validate_logging(
        assertHasAction, CONTROLLABLE_ACTION_TYPE, succeeded=False,
    )
    def test_failed(self, logger):
        """
        If the change passed to ``run_state_change`` returns a ``Deferred``
        that fails, the ``Deferred`` returned by ``run_state_change`` fails the
        same way.
        """
        action = ControllableAction(result=fail(Exception("Oh no")))
        action._logger = logger
        failure = self.failureResultOf(run_state_change(action, DEPLOYER))
        self.assertEqual(failure.getErrorMessage(), "Oh no")
