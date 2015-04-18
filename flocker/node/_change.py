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

from zope.interface import Interface, implementer

from pyrsistent import PVector, PRecord, pvector, field

from twisted.internet.defer import succeed

from ..common import gather_deferreds


class IStateChange(Interface):
    """
    An operation that changes local state.
    """
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
    return change.run(deployer)


@implementer(IStateChange)
class _InParallel(PRecord):
    changes = field(type=PVector, factory=pvector, mandatory=True)

    def run(self, deployer):
        return gather_deferreds(
            [change.run(deployer) for change in self.changes])


def in_parallel(changes):
    """
    Run a series of changes in parallel.

    Failures in one change do not prevent other changes from continuing.
    """
    return _InParallel(changes=changes)


@implementer(IStateChange)
class _Sequentially(PRecord):
    changes = field(type=PVector, factory=pvector, mandatory=True)

    def run(self, deployer):
        d = succeed(None)
        for change in self.changes:
            d.addCallback(lambda _, change=change: change.run(deployer))
        return d


def sequentially(changes):
    """
    Run a series of changes in sequence, one after the other.

    Failures in earlier changes stop later changes.
    """
    return _Sequentially(changes=changes)
