# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Testing utilities for ``flocker.node``.
"""

from socket import socket
from unittest import skipIf

from twisted.python.procutils import which

from ..testtools import loop_until
from .gear import GEAR_PORT


def _gear_running():
    """
    Return whether gear is running on this machine.

    :return: ``True`` if gear can be reached, otherwise ``False``.
    """
    if not which("gear"):
        return False
    sock = socket()
    try:
        return not sock.connect_ex((b'127.0.0.1', GEAR_PORT))
    finally:
        sock.close()
if_gear_configured = skipIf(not _gear_running(),
                            "Must run on machine with `gear daemon` running.")


def wait_for_unit_state(gear_client, unit_name, expected_activation_states):
    """
    Wait until a unit is in the requested state.

    :param gear_client: A ``GearClient`` instance.
    :param unicode unit_name: The name of the unit.
    :param expected_activation_states: Activation states to wait for.

    :return: ``Deferred`` that fires when required state has been reached.
    """
    def is_in_states(units):
        return [unit for unit in units if
                (unit.name == unit_name and
                 unit.activation_state in expected_activation_states)]

    def check_if_in_states():
        responded = gear_client.list()
        responded.addCallback(is_in_states)
        return responded

    return loop_until(check_if_in_states)
