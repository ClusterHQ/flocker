# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
A library for implementing state changes on external systems in an isolated
way.

The basic unit of an external system change provided is an ``IStateChange``
provider.

More complex changes can be composed from individual ``IStateChange``
providers.

``run_state_change`` can be used to execute such a complex collection of
changes.
"""

from zope.interface import Interface, Attribute, implementer

from pyrsistent import PVector, PRecord, pvector, field

from twisted.internet.defer import maybeDeferred, succeed

from eliot.twisted import DeferredContext

from ..common import gather_deferreds


class IStateChange(Interface):
    """
    An operation that changes local state.
    """
    eliot_action = Attribute(
        "An ``eliot.ActionType`` within the context of which to execute this "
        "state change's run method."
    )

    def run(deployer):
        """
        Apply the change to local state.

        :param IDeployer deployer: The ``IDeployer`` to use. Specific
            ``IStateChange`` providers may require specific ``IDeployer``
            providers that provide relevant functionality for applying the
            change.

        :return: ``Deferred`` firing when the change is done.
        """

    def __eq__(other):
        """
        Return whether this change is equivalent to another.
        """

    def __ne__(other):
        """
        Return whether this change is not equivalent to another.
        """


def run_state_change(change, deployer):
    """
    Apply the change to local state.

    :param change: Either an ``IStateChange`` provider or the result of an
        ``in_parallel`` or ``sequentially`` call.
    :param IDeployer deployer: The ``IDeployer`` to use.  Specific
        ``IStateChange`` providers may require specific ``IDeployer`` providers
        that provide relevant functionality for applying the change.

    :return: ``Deferred`` firing when the change is done.
    """
    if isinstance(change, _InParallel):
        return gather_deferreds(list(
            run_state_change(subchange, deployer)
            for subchange in change.changes
        ))
    if isinstance(change, _Sequentially):
        d = succeed(None)
        for subchange in change.changes:
            d.addCallback(
                lambda _, subchange=subchange: run_state_change(
                    subchange, deployer
                )
            )
        return d

    with change.eliot_action.context():
        context = DeferredContext(maybeDeferred(change.run, deployer))
        context.addActionFinish()
        return context.result


# run_state_change doesn't use the IStateChange implementation provided by
# _InParallel and _Sequentially but those types provide it anyway because
# certain other areas of the test suite depend on it.
@implementer(IStateChange)
class _InParallel(PRecord):
    changes = field(
        type=PVector,
        # Sort the changes for the benefit of comparison.  Stick with a vector
        # (rather than, say, a set) in case someone wants to run the same
        # change multiple times in parallel.
        factory=lambda changes: pvector(sorted(changes)),
        mandatory=True
    )

    # Supplied so we technically conform to the interface.  This won't actually
    # be used.
    eliot_action = None

    def run(self, deployer):
        return run_state_change(self, deployer)


def in_parallel(changes):
    """
    Run a series of changes in parallel.

    Failures in one change do not prevent other changes from continuing.

    The order in which execution of the changes is started is unspecified.
    Comparison of the resulting object disregards the ordering of the changes.
    """
    return _InParallel(changes=changes)


# See comment above _InParallel.
@implementer(IStateChange)
class _Sequentially(PRecord):
    changes = field(type=PVector, factory=pvector, mandatory=True)

    # See comment for _InParallel.eliot_action.
    eliot_action = None

    def run(self, deployer):
        return run_state_change(self, deployer)


def sequentially(changes):
    """
    Run a series of changes in sequence, one after the other.

    Failures in earlier changes stop later changes.
    """
    return _Sequentially(changes=changes)
