# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
The command-line certificate authority tool.
"""

from twisted.python.usage import Options


class InitializeOptions(Options):
    """
    Command line for ``flocker-ca initialize``.
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
        pass  # self["name"] =  name

    def run(self):
        # Check if files already exist in current directory. If they do
        # error out. Otherwise calling APIs on CertificateAuthority,
        # create new private/public key pair, self-sign, write out to
        # files locally.
        pass


#@flocker_standard_options
class CAOptions(Options):
    """
    Command line options for ``flocker-ca``.
    """
    longdesc = """flocker-ca is used to create TLS certificates.

    The certificates are used to identify the control service, nodes and
    API clients within a Flocker cluster.
    """

    synoposis = "Usage: flocker-ca [OPTIONS]"

    subCommands = [
        ["initialize", None, InitializeOptions,
         "Initialize a certificate authority in the current working directory."]
        ]


#@implementer(ICommandLineScript):
class CAScript(object):
    """
    Command-line script for ``flocker-ca``.
    """
    def main(self, reactor, options):
        if options.subCommand is not None:
            return maybeDeferred(options.subOptions.run)
        else:
            return self.opt_help()


def flocker_ca_main():
    return FlockerScriptRunner(
        CAScript(), CAOptions(), logging=False).main()
