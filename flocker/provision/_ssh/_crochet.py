from effect import ComposedDispatcher

from .._effect import dispatcher
from ._fabric import dispatcher as fabric_dispatcher


dispatcher = ComposedDispatcher([
    fabric_dispatcher,
    dispatcher,
])
