# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Script for starting control service server.
"""

from twisted.python.usage import Options
from twisted.internet.endpoints import TCP4ServerEndpoint
from twisted.python.filepath import FilePath
from twisted.application.service import MultiService

from .httpapi import create_api_service
from ._persistence import ConfigurationPersistenceService
from ._clusterstate import ClusterStateService
from ..common.script import (
    flocker_standard_options, FlockerScriptRunner, main_for_service)


@flocker_standard_options
class ControlOptions(Options):
    """
    Command line options for ``flocker-control`` cluster management process.
    """
    optParameters = [
        ["data-path", "d", FilePath(b"/var/lib/flocker"),
         "The directory where data will be persisted.", FilePath],
        ["port", "p", 4523, "The external API port to listen on.", int],
        # FLOC-1281 Add option for internal AMP port.
        ]


class ControlScript(object):
    """
    A command to start a long-running process to control a Flocker
    cluster.
    """
    def main(self, reactor, options):
        # FLOC-1281 also add ControlAMPService
        top_service = MultiService()
        persistence = ConfigurationPersistenceService(
            reactor, options["data-path"])
        persistence.setServiceParent(top_service)
        cluster_state = ClusterStateService()
        cluster_state.setServiceParent(top_service)
        create_api_service(persistence, cluster_state, TCP4ServerEndpoint(
            reactor, options["port"])).setServiceParent(top_service)
        return main_for_service(reactor, top_service)


def flocker_control_main():
    return FlockerScriptRunner(
        script=ControlScript(),
        options=ControlOptions()
    ).main()
