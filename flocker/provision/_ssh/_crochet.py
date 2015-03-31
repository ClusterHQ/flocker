from crochet import setup, run_in_reactor
from effect import ComposedDispatcher

from .._effect import dispatcher
from ._conch import dispatcher as conch_dispatcher
from effect.twisted import (
    make_twisted_dispatcher,
    perform as perform_with_twisted
)
from twisted.internet import reactor


def perform(dispatcher, effect):
    """
    Perform an effect in a reactor with crochet.
    """
    setup()
    return run_in_reactor(perform_with_twisted)(
        dispatcher,
        effect,
    ).wait()


dispatcher = ComposedDispatcher([
    conch_dispatcher,
    make_twisted_dispatcher(reactor),
    dispatcher,
])
