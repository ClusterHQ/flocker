# Copyright ClusterHQ Inc.  See LICENSE file for details.
# -*- test-case-name: flocker.control.test.test_script -*-

"""
Script for starting control service server.
"""

import cProfile
import signal
import time

from twisted.python.usage import Options
from twisted.internet.endpoints import serverFromString
from twisted.python.filepath import FilePath
from twisted.application.service import MultiService

from .httpapi import create_api_service, REST_API_PORT
from ._persistence import ConfigurationPersistenceService
from ._clusterstate import ClusterStateService
from ..common.script import (
    flocker_standard_options, FlockerScriptRunner, main_for_service)
from ._protocol import ControlAMPService

DEFAULT_CERTIFICATE_PATH = b"/etc/flocker"


@flocker_standard_options
class ControlOptions(Options):
    """
    Command line options for ``flocker-control`` cluster management process.
    """
    optParameters = [
        ["data-path", "d", FilePath(b"/var/lib/flocker"),
         "The directory where data will be persisted.", FilePath],
        ["port", "p", 'tcp:%d' % (REST_API_PORT,),
         "The external API port to listen on."],
        ["agent-port", "a", 'tcp:4524',
         "The port convergence agents will connect to."],
        ["certificates-directory", "c", DEFAULT_CERTIFICATE_PATH,
         ("Absolute path to directory containing the cluster "
          "root certificate (cluster.crt) and control service certificate "
          "and private key (control-service.crt and control-service.key).")],
    ]


class ControlScript(object):
    """
    A command to start a long-running process to control a Flocker
    cluster.
    """
    def service(
        self, reactor,
        data_path,
        api_port,
        agent_port,
    ):
        """
        :param reactor: The reactor to use for the service.
        :param data_path: The path to store persistent state in.
        :param IServerEndpoint api_port: The endpoint for the API to use.
        :param agent_port: The endpoint description of the agent port to use.
        :param Certificate ca_certificate: The CA certificate of the cluster.
        :param ControlCredential control_credential: The credentials for the
            control service.
        """
        top_service = MultiService()
        persistence = ConfigurationPersistenceService(
            reactor, data_path)
        persistence.setServiceParent(top_service)
        persistence.setServiceParent(top_service)
        cluster_state = ClusterStateService(reactor)
        cluster_state.setServiceParent(top_service)
        api_service = create_api_service(
            persistence, cluster_state, api_port)
        api_service.setServiceParent(top_service)
        amp_service = ControlAMPService(
            reactor, cluster_state, persistence, agent_port,
        )
        amp_service.setServiceParent(top_service)
        return top_service

    def main(self, reactor, options):
        service = self.service(
            reactor,
            data_path=options["data-path"],
            api_port=serverFromString(reactor, options["port"]),
            agent_port=serverFromString(reactor, options["agent-port"]),
        )
        return main_for_service(reactor, service)


def flocker_control_main():
    # Use CPU time instead of wallclock time.
    # The control service does a lot of waiting and we do not
    # want the profiler to include that.
    pr = cProfile.Profile(time.clock)

    def enable_profiling(signal, frame):
        """
        Enable profiling of the control service.

        :param int signal: See ``signal.signal``.
        :param frame: None or frame object. See ``signal.signal``.
        """
        pr.enable()

    def disable_profiling(signal, frame):
        """
        Disable profiling of the control service.
        Dump profiling statistics to a file.

        :param int signal: See ``signal.signal``.
        :param frame: None or frame object. See ``signal.signal``.
        """
        current_time = time.strftime("%Y%m%d%H%M%S")
        path = FilePath('/var/lib/flocker/profile-{}'.format(current_time))
        # This dumps the current profiling statistics and disables the
        # collection of profiling data. When the profiler is next enabled
        # the new statistics are added to existing data.
        pr.dump_stats(path.path)

    signal.signal(signal.SIGUSR1, enable_profiling)
    signal.signal(signal.SIGUSR2, disable_profiling)

    return FlockerScriptRunner(
        script=ControlScript(),
        options=ControlOptions()
    ).main()
