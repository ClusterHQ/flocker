# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Testing utilities for ``flocker.node``.
"""

from unittest import skipIf
from subprocess import Popen

from ..testtools import loop_until

# This is terible (https://github.com/ClusterHQ/flocker/issues/85):
if_docker_configured = skipIf(Popen([b"docker", b"version"]).wait(),
                               "Docker must be installed and running.")


def wait_for_unit_state(docker_client, unit_name, expected_activation_states):
    """
    Wait until a unit is in the requested state.

    :param docker_client: A ``DockerClient`` instance.
    :param unicode unit_name: The name of the unit.
    :param expected_activation_states: Activation states to wait for.

    :return: ``Deferred`` that fires when required state has been reached.
    """
    def is_in_states(units):
        for unit in units:
            if unit.name == unit_name:
                if unit.activation_state in expected_activation_states:
                    return True

    def check_if_in_states():
        responded = docker_client.list()
        responded.addCallback(is_in_states)
        return responded

    return loop_until(check_if_in_states)
