from crochet import setup, run_in_reactor
from effect import (
    ComposedDispatcher, TypeDispatcher, base_dispatcher)

from .._effect import Sequence, perform_sequence
from ._conch import perform_run_remotely
from effect.twisted import (
    make_twisted_dispatcher,
    perform as perform_with_twisted
)
from _model import RunRemotely

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
    TypeDispatcher({
        Sequence: perform_sequence,
        RunRemotely: perform_run_remotely,
    }),
    make_twisted_dispatcher(reactor),
    base_dispatcher,
]),
