# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
The command-line ``flocker-deploy`` tool.
"""

import os
import sys
from json import dumps

from twisted.internet.defer import succeed
from twisted.python.filepath import FilePath
from twisted.python.usage import Options, UsageError
from twisted.web.http import OK

from treq import json_content

from zope.interface import implementer

from yaml import safe_load
from yaml.error import YAMLError

from characteristic import attributes

from ..common.script import (flocker_standard_options, ICommandLineScript,
                             FlockerScriptRunner)
from ..control.httpapi import REST_API_PORT
from ..ca import treq_with_authentication


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

    optParameters = [
        ["port", "p", REST_API_PORT,
         "The REST API port on the server.", int],
        ["cacert", None, None,
         "Path to cluster certificate file."],
        ["cert", None, None,
         "Path to user certificate file."],
        ["key", None, None,
         "Path to user private key file."],
        ["certificates-directory", "c",
         None, ("Path to directory containing TLS certificates and keys. "
                "Defaults to current directory.")],
    ]

    def parseArgs(self, control_host, deployment_config, application_config):
        deployment_config = FilePath(deployment_config)
        application_config = FilePath(application_config)

        if not deployment_config.exists():
            raise UsageError('No file exists at {path}'
                             .format(path=deployment_config.path))

        if not application_config.exists():
            raise UsageError('No file exists at {path}'
                             .format(path=application_config.path))

        self["url"] = u"https://{}:{}/v1/configuration/_compose".format(
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

        for credential, default_path in {
            "cacert": b"cluster.crt",
            "cert": b"user.crt",
            "key": b"user.key",
        }.items():
            if self[credential] is None:
                self[credential] = FilePath(default_path)
            else:
                if self["certificates-directory"] is not None:
                    raise UsageError(
                        "Cannot use --certificates-directory and "
                        "--{credential} options together. Please specify "
                        "either certificates directory or full paths to each "
                        "file via the --cacert, --cert and --key "
                        "options.".format(credential=credential)
                    )
                self[credential] = FilePath(self[credential])

        if self["certificates-directory"] is None:
            self["certificates-directory"] = FilePath(os.getcwd())
        else:
            # Use the directory set by certificates-directory and the
            # default credential file names, which have already been set
            # against the relevant option keys.
            self["certificates-directory"] = FilePath(
                self["certificates-directory"])
            self["cacert"] = self["certificates-directory"].child(
                self["cacert"].basename())
            self["cert"] = self["certificates-directory"].child(
                self["cert"].basename())
            self["key"] = self["certificates-directory"].child(
                self["key"].basename())

        for credential in ["cacert", "cert", "key"]:
            if not self[credential].isfile():
                raise UsageError(
                    "File " + self[credential].path + " does not exist. "
                    "Use the flocker-ca command to create the credential, "
                    "or use the --" + credential +
                    " flag to specify the credential location."
                )


@implementer(ICommandLineScript)
class DeployScript(object):
    """
    A script to start configured deployments on a Flocker cluster.
    """
    def main(self, reactor, options):
        """
        See :py:meth:`ICommandLineScript.main` for parameter documentation.

        :return: A ``Deferred`` which fires when the deployment is complete or
                 has encountered an error.
        """
        body = dumps({"applications": options["application_config"],
                      "deployment": options["deployment_config"]})

        treq_client = treq_with_authentication(
            reactor, options["cacert"], options["cert"], options["key"])
        posted = treq_client.post(
            options["url"], data=body,
            headers={b"content-type": b"application/json"},
            persistent=False
        )

        def fail(msg):
            raise SystemExit(msg)

        def got_response(response):
            if response.code != OK:
                d = json_content(response)

                def got_error(error):
                    if isinstance(error, dict):
                        error = error[u"description"] + u"\n"
                    else:
                        error = u"Unknown error: " + unicode(error) + "\n"
                    fail(error)
                d.addCallback(got_error)
                return d
            else:
                sys.stdout.write(_OK_MESSAGE)
        posted.addCallback(got_response)
        return posted


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
