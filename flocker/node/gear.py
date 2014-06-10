"""Client implementation for talking to the geard daemon."""


from twisted.interface import Interface


class GearClient(Interface):
    """A client for the geard HTTP API."""

    def start(unit_name):
        """"""
