# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Various utilities to help with unit and functional testing."""

from __future__ import absolute_import

from random import random
from collections import namedtuple

from zope.interface import implementer
from zope.interface.verify import verifyClass

from twisted.internet.interfaces import IProcessTransport, IReactorProcess
from twisted.internet.task import Clock, deferLater
from twisted.internet.defer import maybeDeferred
from twisted.internet import reactor


@implementer(IProcessTransport)
class FakeProcessTransport(object):
    """
    Mock process transport to observe signals sent to a process.

    @ivar signals: L{list} of signals sent to process.
    """

    def __init__(self):
        self.signals = []


    def signalProcess(self, signal):
        self.signals.append(signal)



class SpawnProcessArguments(namedtuple('ProcessData',
                  'processProtocol executable args env path '
                  'uid gid usePTY childFDs transport')):
    """
    Object recording the arguments passed to L{FakeProcessReactor.spawnProcess}
    as well as the L{IProcessTransport} that was connected to the protocol.

    @ivar transport: Fake transport connected to the protocol.
    @type transport: L{IProcessTransport}

    @see L{twisted.internet.interfaces.IReactorProcess.spawnProcess}
    """



@implementer(IReactorProcess)
class FakeProcessReactor(Clock):
    """
    Fake reactor implmenting process support.

    @ivar processes: List of process that have been spawned
    @type processes: L{list} of L{SpawnProcessArguments}.
    """

    def __init__(self):
        Clock.__init__(self)
        self.processes = []


    def timeout(self):
        if self.calls:
            return max(0, self.calls[0].getTime() - self.seconds())
        return 0


    def spawnProcess(self, processProtocol, executable, args=(), env={},
                     path=None, uid=None, gid=None, usePTY=0, childFDs=None):
        transport = FakeProcessTransport()
        self.processes.append(SpawnProcessArguments(
            processProtocol, executable, args, env, path, uid, gid, usePTY,
            childFDs, transport=transport))
        processProtocol.makeConnection(transport)
        return transport


verifyClass(IReactorProcess, FakeProcessReactor)


def loop_until(arg, predicate):
    """Call predicate every 0.1 seconds, until it returns ``True``.

    This should only be used in functional tests.

    :param arg: Value to return.
    :param predicate: Callable returning termination condition.
    :type predicate: 0-argument callable returning a Deferred.

    :return: A ``Deferred`` firing with ``arg``
    """
    d = maybeDeferred(predicate)
    def loop(result):
        if not result:
            d = deferLater(reactor, 0.1, predicate)
            d.addCallback(loop)
            return d
        return arg
    d.addCallback(loop)
    return d


def random_name():
    """Return a short, random name.

    :return name: A random ``unicode`` name.
    """
    return u"%d" % (int(random() * 1e12),)
