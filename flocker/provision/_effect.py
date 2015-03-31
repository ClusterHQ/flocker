import sys
from characteristic import attributes
from effect import (
    sync_performer, Effect,
    ComposedDispatcher, TypeDispatcher, base_dispatcher)
from effect.do import do, do_return


# This should be upstream.


@attributes(['results', 'error'])
class SequenceFailed(Exception, object):
    """
    Raised if an effect in a :class:``Sequence`` fails.

    :ivar list results: The list of succesful results.
    :ivar error: The error result of the last run effect.
    """


@attributes(["effects"])
class Sequence(object):
    """
    Runs a sequence of effects serially.

    :returns list: The list of results of the effects.
    :raises SequenceFailed: If one of the ffects fails.
    """


@sync_performer
@do
def perform_sequence(dispatcher, intent):
    results = []
    for effect in list(intent.effects):
        try:
            result = yield effect
            results.append(result)
        except:
            raise SequenceFailed(results=results,
                                 error=sys.exc_info())

    yield do_return(results)


def sequence(effects):
    return Effect(Sequence(effects=effects))


dispatcher = ComposedDispatcher([
    TypeDispatcher({
        Sequence: perform_sequence,
    }),
    base_dispatcher,
])
