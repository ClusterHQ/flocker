# Copyright ClusterHQ Inc.  See LICENSE file for details.
# -*- test-case-name: flocker.control.test.test_script -*-

"""
Script for starting control service server.
"""

import cProfile
import signal
from functools import partial
from time import clock

from pyrsistent import PClass, field

from twisted.python.usage import Options, UsageError
from twisted.internet.endpoints import serverFromString
from twisted.python.filepath import FilePath
from twisted.application.service import MultiService
from twisted.internet.ssl import Certificate

from .httpapi import create_api_service, REST_API_PORT
from ._persistence import ConfigurationPersistenceService
from ._clusterstate import ClusterStateService
from .configuration_store.directory import directory_store_from_options
from .configuration_store.sql import sql_store_from_options
from ..common.script import (
    flocker_standard_options, FlockerScriptRunner, main_for_service,
    enable_profiling, disable_profiling)
from ._protocol import ControlAMPService
from ..ca import (
    rest_api_context_factory, ControlCredential, amp_server_context_factory,
)

DEFAULT_CERTIFICATE_PATH = b"/etc/flocker"


class ConfigurationStorePlugin(PClass):
    """
    Map a configuration storage plugin name to the plugin factory and the
    command line options expected by that plugin.

    :ivar unicode name: The plugin name which is expected on the command line.
    :ivar factory: A callable which will be supplied with the ``Options`` and
        which returns a plugin.
    :ivar list options: A list of tuples in ``twisted.python.usage`` format,
        defining the expected command line options for this plugin.
    """
    name = field(mandatory=True, type={unicode})
    factory = field(mandatory=True)
    options = field(mandatory=True)

    def __unicode__(self):
        """
        This is here so that ``twisted.python.usage.Options`` displays a plugin
        name rather than ``ConfigurationStorePlugin.__repr__``.

        :returns: The name of the plugin.
        """
        return self.name


# A list of available configuration store plugins.
# The first plugin is the default.
CONFIGURATION_STORE_PLUGINS = [
    ConfigurationStorePlugin(
        name=u"directory",
        factory=directory_store_from_options,
        options=[[
            "data-path", "d", FilePath(b"/var/lib/flocker"),
            "The directory where data will be persisted.", FilePath
        ]],

    ),
    ConfigurationStorePlugin(
        name=u"sql",
        factory=sql_store_from_options,
        options=[[
            "database-url",
            None,
            "sqlite:////var/lib/flocker/current_configuration.sqlite",
            (
                "An SQLAlchemy database URL. "
                "Only valid when using --configuration-store-plugin=sql. "
            ),
        ]],
    ),
]
CONFIGURATION_STORE_PLUGINS_BY_NAME = {
    p.name: p for p in CONFIGURATION_STORE_PLUGINS
}
CONFIGURATION_STORE_PLUGIN_NAMES = [
    p.name for p in CONFIGURATION_STORE_PLUGINS
]
CONFIGURATION_STORE_PLUGIN_DEFAULT = CONFIGURATION_STORE_PLUGINS[0]


def validate_configuration_plugin_name(plugin_name):
    """
    :raises: UsageError unless ``plugin_name`` matches a known
        ``ConfigurationStorePlugin``.
    :returns: The ``ConfigurationStorePlugin`` for the supplied name.
    """
    plugin = CONFIGURATION_STORE_PLUGINS_BY_NAME.get(plugin_name)
    if plugin is None:
        raise UsageError(
            "Unrecognized value for --configuration-store-plugin '{}'".format(
                plugin_name
            )
        )
    return plugin


@flocker_standard_options
class ControlOptions(Options):
    """
    Command line options for ``flocker-control`` cluster management process.
    """
    optParameters = [
        ["configuration-store-plugin", None,
         CONFIGURATION_STORE_PLUGIN_DEFAULT,
         u"The plugin to use for storing Flocker configuration. "
         u"One of '{}'.".format(
             "', '".join(CONFIGURATION_STORE_PLUGIN_NAMES)
         ), validate_configuration_plugin_name],
        ["port", "p", 'tcp:%d' % (REST_API_PORT,),
         "The external API port to listen on."],
        ["agent-port", "a", 'tcp:4524',
         "The port convergence agents will connect to."],
        ["certificates-directory", "c", DEFAULT_CERTIFICATE_PATH,
         ("Absolute path to directory containing the cluster "
          "root certificate (cluster.crt) and control service certificate "
          "and private key (control-service.crt and control-service.key).")],
    ]

    for plugin in CONFIGURATION_STORE_PLUGINS:
        optParameters.extend(plugin.options)


class ControlScript(object):
    """
    A command to start a long-running process to control a Flocker
    cluster.
    """
    def main(self, reactor, options):
        store_plugin = options["configuration-store-plugin"]
        store = store_plugin.factory(
            reactor=reactor,
            options=options
        )

        d = ConfigurationPersistenceService.from_store(
            reactor=reactor,
            store=store
        )
        return d.addCallback(
            self._setup_services,
            reactor=reactor,
            options=options,
        )

    def _setup_services(self, persistence, reactor, options):
        certificates_path = FilePath(options["certificates-directory"])
        ca = Certificate.loadPEM(
            certificates_path.child(b"cluster.crt").getContent())
        # This is a hack; from_path should be more
        # flexible. https://clusterhq.atlassian.net/browse/FLOC-1865
        control_credential = ControlCredential.from_path(
            certificates_path, b"service")

        top_service = MultiService()
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
    # Use CPU time instead of wallclock time.
    # The control service does a lot of waiting and we do not
    # want the profiler to include that.
    pr = cProfile.Profile(clock)

    signal.signal(signal.SIGUSR1, partial(enable_profiling, pr))
    signal.signal(signal.SIGUSR2, partial(disable_profiling, pr, 'control'))

    return FlockerScriptRunner(
        script=ControlScript(),
        options=ControlOptions()
    ).main()
