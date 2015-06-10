# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
The command-line certificate authority tool.
"""

import os
import sys

import textwrap

from twisted.internet.defer import maybeDeferred, succeed
from twisted.python.filepath import FilePath
from twisted.python.usage import Options, UsageError

from zope.interface import implementer

from ..common.script import (flocker_standard_options, ICommandLineScript,
                             FlockerScriptRunner)

from ._ca import (RootCredential, ControlCredential, NodeCredential,
                  UserCredential, CertificateAlreadyExistsError,
                  KeyAlreadyExistsError, PathError)


class PrettyOptions(Options):
    """
    Base class with improved output formatting for help text over
    ``twisted.python.usage.Options``. Includes ``self.helptext`` attribute
    in the wrapped help output of a CLI. Use ``self.helptext`` in place of
    ``self.longdesc``.

    A similar solution can be upstreamed to Twisted to fix ``self.longdesc``.
    https://twistedmatrix.com/trac/ticket/7864
    """
    def __str__(self):
        base = super(PrettyOptions, self).__str__()
        helptext = self.helptext if getattr(self, "helptext", None) else ""
        helptext_list = helptext.splitlines()
        description_list = []
        for line in helptext_list:
            description_list.append('\n'.join(textwrap.wrap(line, 80)).strip())
        description = '\n'.join(description_list)
        return base + description

    def getSynopsis(self):
        """
        Modified from ``twisted.python.usage.Options.getSynopsis``.

        Does not include the parent synopsis if inside a subcommand.
        This allows separate synopses to be defined for each subcommand and
        the parent command, facilitating a prettier output, e.g.

        flocker-ca --help
        Usage: flocker-ca <command> [options]

        flocker-ca initialize --help
        Usage: flocker-ca initialize <name>

        Instead of:

        flocker-ca --help
        Usage: flocker-ca <command> [options]

        flocker-ca initialize --help
        Usage: flocker-ca <command> [options] initialize <name>

        Returns a string containing a description of these options and how to
        pass them to the executed file.
        """

        default = "%s%s" % (os.path.basename(sys.argv[0]),
                            (self.longOpt and " [options]") or '')
        if self.parent is None:
            default = "Usage: %s%s" % (os.path.basename(sys.argv[0]),
                                       (self.longOpt and " [options]") or '')
        else:
            default = '%s' % ((self.longOpt and "[options]") or '')
        synopsis = getattr(self, "synopsis", default)

        synopsis = synopsis.rstrip()

        if self.parent is not None:
            commandName = getattr(
                self.parent, "command_name", os.path.basename(sys.argv[0]))
            synopsis = "Usage: %s %s" % (
                commandName, ' '.join((self.parent.subCommand, synopsis)))

        return synopsis

    def getUsage(self, width=None):
        base = super(PrettyOptions, self).getUsage(width)
        usage = base
        if self.subCommand is not None:
            subUsage = (
                "Run flocker-ca "
                + self.subCommand +
                " --help for command usage and help."
            )
            usage = usage + "\n\n" + subUsage + "\n\n"
        return usage


@flocker_standard_options
class UserCertificateOptions(PrettyOptions):
    """
    Command line options for ``flocker-ca create-api-certificate``.
    """

    helptext = """Create a new certificate for an API end user.

    Creates a certificate signed by a previously generated certificate
    authority (see flocker-ca initialize command for more information).

    Usage:

    flocker-ca create-api-certificate <username>

    Parameters:

    * username: A username for which the certificate should be created.
    """

    synopsis = "<name> [options]"

    optParameters = [
        ['inputpath', 'i', None,
         ('Path to directory containing root certificate.'
          'Defaults to current working directory.')],
        ['outputpath', 'o', None,
         ('Path to directory to write control service certificate.'
          'Defaults to current working directory.')],
    ]

    def parseArgs(self, name):
        self["name"] = name

    def run(self):
        """
        Create a new node certificate signed by the root and write it out to
        the current directory.

        :raise PathError: When the root certificate and key cannot be found.
        """
        if self["inputpath"] is None:
            self["inputpath"] = os.getcwd()
        if self["outputpath"] is None:
            self["outputpath"] = os.getcwd()

        self["inputpath"] = FilePath(self["inputpath"])
        self["outputpath"] = FilePath(self["outputpath"])

        try:
            try:
                self["name"] = self["name"].decode("utf-8")
                ca = RootCredential.from_path(self["inputpath"])
                uc = UserCredential.initialize(
                    self["outputpath"], ca, self["name"])
                self._sys_module.stdout.write(
                    u"Created {user}.crt. You can now give it to your "
                    u"API enduser so they can access the control service "
                    u"API.\n".format(user=uc.username).encode("utf-8")
                )
            except PathError as e:
                raise UsageError(str(e))
            except (UnicodeEncodeError, UnicodeDecodeError):
                raise UsageError(
                    u"Invalid username: Could not be converted to UTF-8")
        except UsageError as e:
            raise SystemExit(u"Error: {error}".format(error=str(e)))
        return succeed(None)


@flocker_standard_options
class NodeCertificateOptions(PrettyOptions):
    """
    Command line options for ``flocker-ca create-node-certificate``.
    """

    helptext = """Create a new certificate for a node agent.

    Creates a certificate signed by a previously generated certificate
    authority (see flocker-ca initialize command for more information).
    """

    synopsis = "[options]"

    optParameters = [
        ['inputpath', 'i', None,
         ('Path to directory containing root certificate. '
          'Defaults to current working directory.')],
        ['outputpath', 'o', None,
         ('Path to directory to write control service certificate. '
          'Defaults to current working directory.')],
    ]

    def run(self):
        """
        Check if root key and certificate files (either default or as
        specified on the command line) exist in the path and error out if
        they do not. If there are no path errors, create a new node
        certificate signed by the root and write it out to the current
        directory.
        """
        if self["inputpath"] is None:
            self["inputpath"] = os.getcwd()
        if self["outputpath"] is None:
            self["outputpath"] = os.getcwd()
        self["inputpath"] = FilePath(self["inputpath"])
        self["outputpath"] = FilePath(self["outputpath"])

        try:
            try:
                ca = RootCredential.from_path(self["inputpath"])
                nc = NodeCredential.initialize(self["outputpath"], ca)
                self._sys_module.stdout.write(
                    u"Created {uuid}.crt. Copy it over to "
                    u"/etc/flocker/node.crt on your node "
                    u"machine and make sure to chmod 0600 it.\n".format(
                        uuid=nc.uuid
                    ).encode("utf-8")
                )
            except PathError as e:
                raise UsageError(str(e))
        except UsageError as e:
            raise SystemExit(u"Error: {error}".format(error=str(e)))
        return succeed(None)


@flocker_standard_options
class ControlCertificateOptions(PrettyOptions):
    """
    Command line options for ``flocker-ca create-control-certificate``.

    Might want to support more than one domain name:
    https://clusterhq.atlassian.net/browse/FLOC-1977
    """

    helptext = """Create a new certificate for the control service.

    Creates a certificate signed by a previously generated certificate
    authority (see flocker-ca initialize command for more information).

    The hostname will be encoded into the generated certificate for
    validation by HTTPS clients, so it should match the external domain
    name of the machine the control service will run on.

    The generated files will be stored in the specified output directory
    (defaults to current working directory) with the names
    "control-<hostname>.crt" and "control-<hostname>.key".

    Usage:

    flocker-ca create-control-certificate <hostname>

    Parameters:

    * hostname: The hostname that this control service's API will run on.
      e.g. "example.org".
    """

    synopsis = "[options] <hostname>"

    optParameters = [
        ['inputpath', 'i', None,
         ('Path to directory containing root certificate. '
          'Defaults to current working directory.')],
        ['outputpath', 'o', None,
         ('Path to directory to write control service certificate. '
          'Defaults to current working directory.')],
    ]

    def parseArgs(self, hostname):
        self["hostname"] = hostname

    def run(self):
        """
        Check if control service certificate already exist in current
        directory. If it does, error out. Also check if root key and
        certificate files (either default or as specified on the command line)
        exist in the path and error out if they do not. If there are no path
        errors, create a new control service certificate signed by the root
        and write it out to the current directory.
        """
        if self["inputpath"] is None:
            self["inputpath"] = os.getcwd()
        if self["outputpath"] is None:
            self["outputpath"] = os.getcwd()
        self["inputpath"] = FilePath(self["inputpath"])
        self["outputpath"] = FilePath(self["outputpath"])

        try:
            try:
                ca = RootCredential.from_path(self["inputpath"])
                ControlCredential.initialize(self["outputpath"], ca,
                                             self["hostname"])
                output_certificate_filename = (
                    b"control-" + self["hostname"] + b".crt").decode("utf-8")
                output_key_filename = (
                    b"control-" + self["hostname"] + b".key").decode("utf-8")
                success_message = (
                    u"Created {certificate} and {key}\n"
                    u"Copy these files to the directory /etc/flocker on your "
                    u"control service machine.\nRename the files to "
                    u"control-service.crt and control-service.key and "
                    u"set the correct permissions by running chmod 0600 on "
                    u"both files."
                    u"\n".format(
                        certificate=output_certificate_filename,
                        key=output_key_filename
                    ).encode("utf-8")
                )
                self._sys_module.stdout.write(success_message)
            except (
                CertificateAlreadyExistsError, KeyAlreadyExistsError, PathError
            ) as e:
                raise UsageError(str(e))
        except UsageError as e:
            raise SystemExit(u"Error: {error}".format(error=str(e)))
        return succeed(None)


@flocker_standard_options
class InitializeOptions(PrettyOptions):
    """
    Command line options for ``flocker-ca initialize``.
    """

    helptext = """Create a new certificate authority.

    Creates a private/public key pair and self-signs the public key to
    produce a new certificate authority root certificate. These are stored
    in the current working directory. Once this has been done other
    ``flocker-ca`` commands can be run in this directory to create
    certificates singed by this particular certificate authority.

    Usage:

    flocker-ca initialize <name>

    Parameters:

    * name: Will be used as the name of the certificate authority,
      e.g. "mycluster".
    """

    synopsis = "<name>"

    def parseArgs(self, name):
        self["name"] = name
        self["path"] = FilePath(os.getcwd())

    def run(self):
        """
        Check if files already exist in current directory. If they do,
        error out. Otherwise calling APIs on CertificateAuthority,
        create new private/public key pair, self-sign, write out to
        files locally.
        """
        try:
            try:
                RootCredential.initialize(self["path"], self["name"])
                self._sys_module.stdout.write(
                    b"Created cluster.key and cluster.crt. "
                    b"Please keep cluster.key secret, as anyone who can "
                    b"access it will be able to control your cluster.\n"
                )
            except (
                KeyAlreadyExistsError, CertificateAlreadyExistsError, PathError
            ) as e:
                raise UsageError(str(e))
        except UsageError as e:
            raise SystemExit(u"Error: {error}".format(error=str(e)))
        return succeed(None)


@flocker_standard_options
class CAOptions(PrettyOptions):
    """
    Command line options for ``flocker-ca``.
    """
    helptext = """flocker-ca is used to create TLS certificates.

    The certificates are used to identify the control service, nodes and
    API clients within a Flocker cluster.
    """
    synopsis = "Usage: flocker-ca <command> [options]"

    subCommands = [
        ["initialize", None, InitializeOptions,
         ("Initialize a certificate authority in the "
          "current working directory.")],
        ["create-control-certificate", None, ControlCertificateOptions,
         "Create a certificate for the control service."],
        ["create-node-certificate", None, NodeCertificateOptions,
         "Create a certificate for a node agent."],
        ["create-api-certificate", None, UserCertificateOptions,
         "Create a certificate for an API user."],
        ]


@implementer(ICommandLineScript)
class CAScript(object):
    """
    Command-line script for ``flocker-ca``.
    """
    def main(self, reactor, options):
        if options.subCommand is not None:
            return maybeDeferred(options.subOptions.run)
        else:
            return options.opt_help()


def flocker_ca_main():
    return FlockerScriptRunner(
        CAScript(), CAOptions(), logging=False).main()
