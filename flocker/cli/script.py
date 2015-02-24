# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
The command-line ``flocker-deploy`` tool.
"""

from subprocess import CalledProcessError

from twisted.internet.defer import DeferredList
from twisted.internet.threads import deferToThread
from twisted.python.filepath import FilePath
from twisted.python.usage import Options, UsageError

from zope.interface import implementer

from yaml import safe_load, safe_dump
from yaml.error import YAMLError

from characteristic import attributes

from ..common.script import (flocker_standard_options, ICommandLineScript,
                             FlockerScriptRunner)
from ..control import (FlockerConfiguration, ConfigurationError,
                       FigConfiguration, applications_to_flocker_yaml,
                       model_from_configuration)

from ..common import ProcessNode, gather_deferreds
from ._sshconfig import DEFAULT_SSH_DIRECTORY, OpenSSHConfiguration


@attributes(['node', 'hostname'])
class NodeTarget(object):
    """
    A record for matching an ``INode`` implementation to its target host.
    """


@flocker_standard_options
class DeployOptions(Options):
    """
    Command line options for ``flocker-deploy``.

    :raises ValueError: If either file supplied does not exist.
    """
    longdesc = """flocker-deploy allows you to configure existing nodes.

    """

    synopsis = ("Usage: flocker-deploy [OPTIONS] "
                "DEPLOYMENT_CONFIGURATION_PATH APPLICATION_CONFIGURATION_PATH"
                "\n"
                "If you have any issues or feedback, you can talk to us: "
                "http://docs.clusterhq.com/en/latest/gettinginvolved/"
                "contributing.html#talk-to-us")

    def parseArgs(self, deployment_config, application_config):
        deployment_config = FilePath(deployment_config)
        application_config = FilePath(application_config)

        if not deployment_config.exists():
            raise UsageError('No file exists at {path}'
                             .format(path=deployment_config.path))

        if not application_config.exists():
            raise UsageError('No file exists at {path}'
                             .format(path=application_config.path))

        self["deployment_config"] = deployment_config.getContent()
        self["application_config"] = application_config.getContent()

        try:
            deploy_config_obj = safe_load(self["deployment_config"])
        except YAMLError as e:
            raise UsageError(
                ("Deployment configuration at {path} could not be parsed as "
                 "YAML:\n\n{error}").format(
                    path=deployment_config.path,
                    error=str(e)
                )
            )
        try:
            app_config_obj = safe_load(self["application_config"])
        except YAMLError as e:
            raise UsageError(
                ("Application configuration at {path} could not be parsed as "
                 "YAML:\n\n{error}").format(
                    path=application_config.path,
                    error=str(e)
                )
            )

        try:
            fig_configuration = FigConfiguration(app_config_obj)
            if fig_configuration.is_valid_format():
                applications = fig_configuration.applications()
                self['application_config'] = (
                    applications_to_flocker_yaml(applications)
                )
            else:
                configuration = FlockerConfiguration(app_config_obj)
                if configuration.is_valid_format():
                    applications = configuration.applications()
                else:
                    raise ConfigurationError(
                        "Configuration is not a valid Fig or Flocker format."
                    )
            self['deployment'] = model_from_configuration(
                applications=applications,
                deployment_configuration=deploy_config_obj)
        except ConfigurationError as e:
            raise UsageError(str(e))


@implementer(ICommandLineScript)
class DeployScript(object):
    """
    A script to start configured deployments on a Flocker cluster.
    """
    def __init__(self, ssh_configuration=None, ssh_port=22):
        if ssh_configuration is None:
            ssh_configuration = OpenSSHConfiguration.defaults()
        self.ssh_configuration = ssh_configuration
        self.ssh_port = ssh_port

    def _configure_ssh(self, deployment):
        """
        :return: A ``Deferred`` which fires when all nodes have been configured
            with ssh keys.
        """
        self.ssh_configuration.create_keypair()
        results = []
        for node in deployment.nodes:
            results.append(
                deferToThread(
                    self.ssh_configuration.configure_ssh,
                    node.hostname, self.ssh_port
                )
            )
        d = gather_deferreds(results)

        # Exit with ssh's output if it failed for some reason:
        def got_failure(failure):
            if failure.value.subFailure.check(CalledProcessError):
                raise SystemExit(
                    b"Error connecting to cluster node: " +
                    failure.value.subFailure.value.output)
            else:
                return failure

        d.addErrback(got_failure)
        return d

    def main(self, reactor, options):
        """
        See :py:meth:`ICommandLineScript.main` for parameter documentation.

        :return: A ``Deferred`` which fires when the deployment is complete or
                 has encountered an error.
        """
        deployment = options['deployment']
        configuring = self._configure_ssh(deployment)
        configuring.addCallback(
            lambda _: self._reportstate_on_nodes(deployment))

        def configured(current_config):
            return self._changestate_on_nodes(
                deployment,
                options["deployment_config"],
                options["application_config"],
                current_config)
        configuring.addCallback(configured)
        configuring.addCallback(lambda _: None)
        return configuring

    def _get_destinations(self, deployment):
        """
        Return iterable of ``NodeTargets`` to connect to for given deployment.

        :param Deployment deployment: The requested already parsed
            configuration.

        :return: Iterable of ``NodeTarget``\ s containing the node hostname and
            corresponding ``INode`` provider with which to issue remote
            procedures on that node.
        """
        private_key = DEFAULT_SSH_DIRECTORY.child(b"id_rsa_flocker")

        for node in deployment.nodes:
            yield NodeTarget(
                node=ProcessNode.using_ssh(
                    node.hostname, 22, b"root", private_key),
                hostname=node.hostname
            )

    def _reportstate_on_nodes(self, deployment):
        """
        Connect to all nodes and run ``flocker-reportstate``.

        :param Deployment deployment: The requested already parsed
            configuration.

        :return: ``Deferred`` that fires with a ``bytes`` in YAML format
            describing the current configuration.
        """
        command = [b"flocker-reportstate"]
        results = []
        for target in self._get_destinations(deployment):
            d = deferToThread(target.node.get_output, command)
            d.addCallback(safe_load)
            d.addCallback(lambda val, key=target.hostname: (key, val))
            results.append(d)
        d = DeferredList(results, fireOnOneErrback=False, consumeErrors=True)

        def got_results(node_states):
            # Bail on errors:
            for succeeded, value in node_states:
                if not succeeded:
                    return value
            return safe_dump(dict(pair for (_, pair) in node_states))
        d.addCallback(got_results)
        return d

    def _changestate_on_nodes(self, deployment, deployment_config,
                              application_config, cluster_config):
        """
        Connect to all nodes and run ``flocker-changestate``.

        :param Deployment deployment: The requested already parsed
            configuration.
        :param bytes deployment_config: YAML-encoded deployment configuration.
        :param bytes application_config: YAML-encoded application
            configuration.
        :param bytes current_config: YAML-encoded current cluster
            configuration.

        :return: ``Deferred`` that fires when all remote calls are finished.
        """
        command = [b"flocker-changestate",
                   deployment_config,
                   application_config,
                   cluster_config]
        results = []
        for target in self._get_destinations(deployment):
            # XXX if number of nodes is bigger than number of available
            # threads we won't get the required parallelism...
            # https://clusterhq.atlassian.net/browse/FLOC-347
            results.append(
                deferToThread(
                    target.node.get_output, command + [target.hostname]))
        return DeferredList(results)


def flocker_deploy_main():
    return FlockerScriptRunner(
        script=DeployScript(),
        options=DeployOptions(),
        logging=False,
    ).main()
