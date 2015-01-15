# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Script for starting control service server.
"""

from twisted.python.usage import Options
from twisted.internet.endpoints import TCP4ServerEndpoint

from .httpapi import create_api_service
from ..common.script import (
    flocker_standard_options, FlockerScriptRunner, main_for_service)


@flocker_standard_options
class ControlOptions(Options):
    """
    Command line options for ``flocker-control`` cluster management process.
    """
    optParameters = [
        ["port", "p", 4523, "The port to listen on.", int],
        ]


class ControlScript(object):
    """
    A command to start a long-running process to control a Flocker
    cluster.
    """
    def main(self, reactor, options):
        api_service = create_api_service(
            TCP4ServerEndpoint(reactor, options["port"]))
        return main_for_service(reactor, api_service)


def flocker_control_main():
    return FlockerScriptRunner(
        script=ControlScript(),
        options=ControlOptions()
    ).main()
