# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
The command-line certificate authority tool.
"""

import os
import sys

from twisted.internet.defer import maybeDeferred, Deferred
from twisted.python.filepath import FilePath
from twisted.python.usage import Options, UsageError

from zope.interface import implementer

from ..common.script import (flocker_standard_options, ICommandLineScript,
                             FlockerScriptRunner)

from ._ca import (CertificateAuthority, ControlCertificate,
                  CertificateAlreadyExistsError, KeyAlreadyExistsError,
                  PathError)


class ControlCertificateOptions(Options):
    """
    Command line options for ``flocker-ca create-control-certificate``.
    """

    longdesc = """Create a new certificate for the control service.

    Creates a certificate signed by a previously generated certificate
    authority (see flocker-ca initialize command for more information).

    The certificate will be stored in the current working directory.

    Parameters:

    * authoritypath: Path to the root certificate's private key. Defaults to
    ./cluster.key
    * certfile: path to the root certificate file. Defaults to ./cluster.crt
    """

    synopsis = "<authoritypath>"

    def parseArgs(self, *args):
        self["path"] = FilePath(os.getcwd())
        self["rootpath"] = FilePath(os.getcwd())
        if len(args) == 1:
            self["rootpath"] = FilePath(args[0])
        if len(args) > 1:
            raise UsageError(
                ("Invalid number of arguments. Run with --help for more "
                 "information.")
            )

    def run(self):
        """
        Check if control service certificate already exist in current
        directory. If it does, error out. Also check if root key and
        certificate files (either default or as specified on the command line)
        exist in the path and error out if they do not. If there are no path
        errors, create a new control service certificate signed by the root
        and write it out to the current directory.
        """
        d = Deferred()

        def generateCert(_):
            try:
                ca = CertificateAuthority.from_path(self["rootpath"])
                ControlCertificate.initialize(self["path"], ca)
                print (
                    b"Created control-service.crt. Copy it over to "
                    "/etc/flocker/control-service.crt on your control service "
                    "machine and make sure to chmod 0600 it."
                )
            except CertificateAlreadyExistsError as e:
                raise UsageError(str(e))
            except PathError as e:
                raise UsageError(str(e))

        def generateError(failure):
            print b"Error: {error}".format(error=str(failure.value))
            sys.exit(1)

        d.addCallback(generateCert)
        d.addErrback(generateError)
        d.callback(None)
        return d


class InitializeOptions(Options):
    """
    Command line options for ``flocker-ca initialize``.
    """

    longdesc = """Create a new certificate authority.

    Creates a private/public key pair and self-signs the public key to
    produce a new certificate authority root certificate. These are stored
    in the current working directory. Once this has been done other
    ``flocker-ca`` commands can be run in this directory to create
    certificates singed by this particular certificate authority.

    Parameters:

    * name: Will be used as the name of the certificate authority,
      e.g. "mycluster".
    """

    synoposis = "<name>"

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
        d = Deferred()

        def generateCert(_):
            try:
                CertificateAuthority.initialize(self["path"], self["name"])
                print (
                    b"Created cluster.key and cluster.crt. "
                    "Please keep cluster.key secret, as anyone who can access "
                    "it will be able to control your cluster."
                )
            except CertificateAlreadyExistsError as e:
                raise UsageError(str(e))
            except KeyAlreadyExistsError as e:
                raise UsageError(str(e))

        def generateError(failure):
            print b"Error: {error}".format(error=str(failure.value))
            sys.exit(1)

        d.addCallback(generateCert)
        d.addErrback(generateError)
        d.callback(None)
        return d


@flocker_standard_options
class CAOptions(Options):
    """
    Command line options for ``flocker-ca``.
    """
    longdesc = """flocker-ca is used to create TLS certificates.

    The certificates are used to identify the control service, nodes and
    API clients within a Flocker cluster.
    """

    synopsis = "Usage: flocker-ca <command> [OPTIONS]"

    subCommands = [
        ["initialize", None, InitializeOptions,
         ("Initialize a certificate authority in the "
          "current working directory.")],
        ["create-control-certificate", None, ControlCertificateOptions,
         "Create a certificate for the control service."],
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
