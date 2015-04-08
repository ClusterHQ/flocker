# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
The command-line ``flocker-deploy`` tool.
"""

import sys
from subprocess import CalledProcessError
from json import dumps

from twisted.internet.threads import deferToThread
from twisted.internet.defer import succeed
from twisted.python.filepath import FilePath
from twisted.python.usage import Options, UsageError
from twisted.web.http import OK

from treq import post, json_content

from zope.interface import implementer

from yaml import safe_load
from yaml.error import YAMLError

from characteristic import attributes

from ..common.script import (flocker_standard_options, ICommandLineScript,
                             FlockerScriptRunner)
from ..common import gather_deferreds
from ._sshconfig import OpenSSHConfiguration
from ..control.httpapi import REST_API_PORT


FEEDBACK_CLI_TEXT = (
    "\n\n"
    "If you have any issues or feedback, you can talk to us: "
    "https://docs.clusterhq.com/en/latest/gettinginvolved/"
    "contributing.html#talk-to-us")

_OK_MESSAGE = (
    b"The cluster configuration has been updated. It may take a short "
    b"while for changes to take effect, in particular if Docker "
    b"images need to be pulled.\n")


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
                "<control-host> <deployment.yml-path> <application.yml-path>"
                "{feedback}").format(feedback=FEEDBACK_CLI_TEXT)

    optFlags = [["nossh", None, "Disable SSH setup stage."]]
    optParameters = [["port", "p", REST_API_PORT,
                      "The REST API port on the server.", int]]

    def parseArgs(self, control_host, deployment_config, application_config):
        deployment_config = FilePath(deployment_config)
        application_config = FilePath(application_config)

        if not deployment_config.exists():
            raise UsageError('No file exists at {path}'
                             .format(path=deployment_config.path))

        if not application_config.exists():
            raise UsageError('No file exists at {path}'
                             .format(path=application_config.path))

        self["url"] = u"http://{}:{}/v1/configuration/_compose".format(
            control_host, self["port"]).encode("ascii")
        self["application_config"] = application_config.getContent()

        try:
            self["deployment_config"] = safe_load(
                deployment_config.getContent())
        except YAMLError as e:
            raise UsageError(
                ("Deployment configuration at {path} could not be parsed as "
                 "YAML:\n\n{error}").format(
                    path=deployment_config.path,
                    error=str(e)
                )
            )
        try:
            self["application_config"] = safe_load(
                application_config.getContent())
        except YAMLError as e:
            raise UsageError(
                ("Application configuration at {path} could not be parsed as "
                 "YAML:\n\n{error}").format(
                    path=application_config.path,
                    error=str(e)
                )
            )


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

    def main(self, reactor, options):
        """
        See :py:meth:`ICommandLineScript.main` for parameter documentation.

        :return: A ``Deferred`` which fires when the deployment is complete or
                 has encountered an error.
        """
        if options["nossh"]:
            ready = succeed(None)
        else:
            ready = self._configure_ssh(
                options["deployment_config"]["nodes"].keys())

        body = dumps({"applications": options["application_config"],
                      "deployment": options["deployment_config"]})
        ready.addCallback(
            lambda _: post(options["url"], data=body,
                           headers={b"content-type": b"application/json"},
                           persistent=False))

        def fail(msg):
            raise SystemExit(msg)

        def got_response(response):
            if response.code != OK:
                d = json_content(response)
                d.addCallback(
                    lambda error: fail(error[u"description"] + u"\n"))
                return d
            else:
                sys.stdout.write(_OK_MESSAGE)
        ready.addCallback(got_response)
        return ready

    def _configure_ssh(self, hostnames):
        """
        :param list hostnames: The addresses of the machines for which to
            configure SSH keys.

        :return: A ``Deferred`` which fires when all nodes have been configured
            with ssh keys.
        """
        self.ssh_configuration.create_keypair()
        results = []
        for hostname in hostnames:
            results.append(
                deferToThread(
                    self.ssh_configuration.configure_ssh,
                    hostname.encode("ascii"), self.ssh_port
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


@flocker_standard_options
class CLIOptions(Options):
    """
    Command line options for ``flocker`` CLI.
    """
    longdesc = ("flocker is under development, please see flocker-deploy "
                "to configure existing nodes.")

    synopsis = "Usage: flocker [OPTIONS] {feedback}".format(
        feedback=FEEDBACK_CLI_TEXT)


@implementer(ICommandLineScript)
class CLIScript(object):
    """
    A command-line script to interact with a cluster via the API.
    """
    def main(self, reactor, options):
        """
        See :py:meth:`ICommandLineScript.main` for parameter documentation.

        :return: A ``Deferred`` which fires when the deployment is complete or
                 has encountered an error.
        """
        return succeed(None)


def flocker_deploy_main():
    return FlockerScriptRunner(
        script=DeployScript(),
        options=DeployOptions(),
        logging=False,
    ).main()


def flocker_cli_main():
    # There is nothing to log at the moment, so logging is disabled.
    return FlockerScriptRunner(
        script=CLIScript(),
        options=CLIOptions(),
        logging=False,
    ).main()
