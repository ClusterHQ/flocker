# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.control.test.test_script -*-

"""
Script for starting control service server.
"""

import cProfile
import pstats
import signal
import StringIO
import time

from twisted.python.usage import Options
from twisted.internet.endpoints import serverFromString
from twisted.python.filepath import FilePath
from twisted.application.service import MultiService
from twisted.internet.ssl import Certificate

from .httpapi import create_api_service, REST_API_PORT
from ._persistence import ConfigurationPersistenceService
from ._clusterstate import ClusterStateService
from ..common.script import (
    flocker_standard_options, FlockerScriptRunner, main_for_service)
from ._protocol import ControlAMPService
from ..ca import (
    rest_api_context_factory, ControlCredential, amp_server_context_factory,
)

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
    def main(self, reactor, options):
        certificates_path = FilePath(options["certificates-directory"])
        ca = Certificate.loadPEM(
            certificates_path.child(b"cluster.crt").getContent())
        # This is a hack; from_path should be more
        # flexible. https://clusterhq.atlassian.net/browse/FLOC-1865
        control_credential = ControlCredential.from_path(
            certificates_path, b"service")

        top_service = MultiService()
        persistence = ConfigurationPersistenceService(
            reactor, options["data-path"])
        persistence.setServiceParent(top_service)
        cluster_state = ClusterStateService(reactor)
        cluster_state.setServiceParent(top_service)
        api_service = create_api_service(
            persistence, cluster_state, serverFromString(
                reactor, options["port"]),
            rest_api_context_factory(ca, control_credential))
        api_service.setServiceParent(top_service)
        amp_service = ControlAMPService(
            reactor, cluster_state, persistence, serverFromString(
                reactor, options["agent-port"]),
            amp_server_context_factory(ca, control_credential))
        amp_service.setServiceParent(top_service)
        return main_for_service(reactor, top_service)


def flocker_control_main():
    # TODO Move this to FlockerScriptRunner
    # TODO Change this so that it is only profiling when a particular
    # environment variable is set
    # TODO Ensure cProfile is providing information about CPU time
    # TODO Can we provide live updates about the performance rather than
    # sending a signal?
    pr = cProfile.Profile()
    pr.enable()

    def output_profile(signal, frame):
        pr.disable()
        s = StringIO.StringIO()
        sortby = 'cumulative'
        ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
        ps.print_stats()
        current_time = time.strftime("%Y%m%d%H%M%S")
        profile_filename = "profile-{}.txt".format(current_time)
        with open(profile_filename, "w") as profile_output:
            profile_output.write(s.getvalue())

    signal.signal(signal.SIGUSR1, output_profile)

    return FlockerScriptRunner(
        script=ControlScript(),
        options=ControlOptions()
    ).main()
