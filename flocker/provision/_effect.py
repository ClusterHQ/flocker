from functools import partial
from six import reraise
from characteristic import attributes
from effect import (
    sync_performer, Effect,
    ComposedDispatcher, TypeDispatcher, base_dispatcher)
from treq import get
from pyrsistent import PClass, field
from txeffect import deferred_performer
from eliot import startAction, Message
from eliot.twisted import DeferredContext


# This is from https://github.com/radix/effect/pull/46

@attributes(['results', 'exc_info'], apply_immutable=True)
class SequenceFailed(Exception, object):
    """
    Raised if an effect in a :class:``Sequence`` fails.

    :ivar list results: The list of successful results.
    :ivar exc_info: The error result of the last run effect.
    """

    def __str__(self):
        # Exception has a custom __str__ that looks at arguments pass to it's
        # init.  Since we don't pass any, it is useless. The following will
        # duplicate the class name in the traceback, but is better than
        # otherwise.
        return repr(self)


@attributes(["effects"], apply_with_init=False, apply_immutable=True)
class Sequence(object):
    """
    Runs a sequence of effects serially.

    :returns list: The list of results of the effects.
    :raises SequenceFailed: If one of the effects fails.
    """

    def __init__(self, effects):
        """
        :param effects: The list of effects to execute in sequence.
        """
        self.effects = effects


def sequence(effects):
    """
    Given multiple Effects, return one Effect that represents the sequence of
    all of their effects.  The result of the aggregate Effect will be a list of
    their results, in the same order as the input to this function. If any
    child effect fails, the first such failure will be propagated as a
    :class:`SequenceFailed` exception.

    :param effects: Effects which should be performed in sequence.
    :return: An Effect that results in a list of results, or which fails with
        a :class:`SequenceFailed`.
    """
    return Effect(Sequence(list(effects)))


@sync_performer
def perform_sequence(dispatcher, intent):
    """Performer for :class:`Sequence`."""
    effects = list(intent.effects)
    if not effects:
        return []
    results = []

    def succeed(next_effect, result):
        results.append(result)
        return next_effect

    def fail(result):
        reraise(SequenceFailed,
                SequenceFailed(results=results, exc_info=result),
                result[2])

    def reducer(next_effect, effect):
        return effect.on(success=partial(succeed, next_effect),
                         error=fail)

    return reduce(reducer, reversed(effects), results)


class HTTPGet(PClass):
    """
    Intent for HTTP GET requests.

    :ivar bytes url: The URL to make a GET request to.
    """
    url = field(type=bytes, mandatory=True)


def http_get(url):
    """
    Wrapper to create an :class:`HTTPGet` Effect.

    :param bytes url: The url to make a GET request to.

    :returns: The ``Effect`` of making a GET request to ``url``.
    """
    return Effect(HTTPGet(url=url))


@deferred_performer
def treq_get(dispatcher, intent):
    """
    Performer to execute an HTTP GET.

    :param dispatcher: The dispatcher used to dispatch this performance.
    :param HTTPGet intent: The intent to be performed.
    """
    action = startAction(action_type=u"flocker:provision:_effect:treq_get")
    with action.context():
        Message.log(url=intent.url)
        # Do not use persistent HTTP connections, because they will not be
        # cleaned up by the end of the test.
        d = DeferredContext(get(intent.url, persistent=False))
        d.addActionFinish()
        return d.result


dispatcher = ComposedDispatcher([
    TypeDispatcher({
        Sequence: perform_sequence,
        HTTPGet: treq_get,
    }),
    base_dispatcher,
])
