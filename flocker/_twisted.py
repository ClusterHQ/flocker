# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Things that should be in Twisted but aren't (yet).

As such all code in this module was released under the following terms:

    Copyright (c) 2001-2013
    Allen Short
    Andy Gayton
    Andrew Bennetts
    Antoine Pitrou
    Apple Computer, Inc.
    Ashwini Oruganti
    Benjamin Bruheim
    Bob Ippolito
    Canonical Limited
    Christopher Armstrong
    David Reid
    Donovan Preston
    Eric Mangold
    Eyal Lotem
    Google Inc.
    Hynek Schlawack
    Itamar Turner-Trauring
    James Knight
    Jason A. Mobarak
    Jean-Paul Calderone
    Jessica McKellar
    Jonathan Jacobs
    Jonathan Lange
    Jonathan D. Simms
    Jurgen Hermann
    Julian Berman
    Kevin Horn
    Kevin Turner
    Laurens Van Houtven
    Mary Gardiner
    Matthew Lefkowitz
    Massachusetts Institute of Technology
    Moshe Zadka
    Paul Swartz
    Pavel Pergamenshchik
    Ralph Meijer
    Richard Wall
    Sean Riley
    Software Freedom Conservancy
    Travis B. Hartwell
    Thijs Triemstra
    Thomas Herve
    Timothy Allen
    Tom Prince

    Permission is hereby granted, free of charge, to any person obtaining
    a copy of this software and associated documentation files (the
    "Software"), to deal in the Software without restriction, including
    without limitation the rights to use, copy, modify, merge, publish,
    distribute, sublicense, and/or sell copies of the Software, and to
    permit persons to whom the Software is furnished to do so, subject to
    the following conditions:

    The above copyright notice and this permission notice shall be
    included in all copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
    EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
    MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
    NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
    LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
    OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
    WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""


# From https://twistedmatrix.com/trac/ticket/5786
def timeoutDeferred(reactor, deferred, seconds):
    """
    Cancel a L{Deferred} if it does not have a result available within the
    given amount of time.

    @see: L{Deferred.cancel}.

    The timeout only waits for callbacks that were added before
    L{timeoutDeferred} was called. If the L{Deferred} is fired then the
    timeout will be removed, even if callbacks added after
    L{timeoutDeferred} are still waiting for a result to become available.

    @type reactor: L{IReactorTime}
    @param reactor: A provider of L{twisted.internet.interfaces.IReactorTime}.

    @type deferred: L{Deferred}
    @param deferred: The L{Deferred} to time out.

    @type seconds: C{float}
    @param seconds: The number of seconds before the timeout will happen.

    @rtype: L{twisted.internet.interfaces.IDelayedCall}
    @return: The scheduled timeout call.
    """
    # Schedule timeout, making sure we know when it happened:
    def timedOutCall():
        deferred.cancel()
    delayedTimeOutCall = reactor.callLater(seconds, timedOutCall)

    # If Deferred has result, cancel the timeout:
    def cancelTimeout(result):
        if delayedTimeOutCall.active():
            delayedTimeOutCall.cancel()
        return result
    deferred.addBoth(cancelTimeout)

    return delayedTimeOutCall
