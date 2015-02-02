# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Sphinx extension to add directives to allow files and code to include the
latest version of Flocker CLI.
"""

from sphinx.directives.code import CodeBlock, LiteralInclude
from sphinx.roles import XRefRole

from flocker import __version__ as version
from flocker.docs import parse_version

from sphinx import addnodes
from sphinx.util import ws_re

CLI_RELEASE = u'|cli-release|'

class VersionDownload(XRefRole):
    """
    Similar to downloadable files, but:
        * Replaces a placeholder in the downloadable file with the latest
          version of the Flocker CLI.
        * Replaces the download link with one which strips '.template' from the
          end of the file name.
    """
    nodeclass = addnodes.download_reference

    def process_link(self, env, refnode, has_explicit_title, title, target):
        parsed_version = parse_version(version)
        latest = parsed_version.client_release
        rel_filename, filename = env.relfn2path(target)
        extension_length = len('.template')
        with open(rel_filename, 'r') as templated_file:
            with open(rel_filename[:-extension_length], 'w') as new_file:
                new_file.write(templated_file.read().replace(CLI_RELEASE, latest))
        return title[:-extension_length], ws_re.sub(' ', target[:-extension_length])


class VersionLiteralInclude(LiteralInclude):
    """
    Similar to LiteralInclude but replaces a placeholder with the latest
    version of the Flocker CLI.

    # Rename this file to version_extensions
    # changes in _version
    # separate out the file replacement code
    # pep8
    """
    def run(self):
        parsed_version = parse_version(version)
        latest = parsed_version.client_release
        document = self.state.document
        env = document.settings.env
        extension_length = len('.template')
        rel_filename, filename = env.relfn2path(self.arguments[0])
        with open(rel_filename, 'r') as templated_file:
            with open(rel_filename[:-extension_length], 'w') as new_file:
                new_file.write(templated_file.read().replace(CLI_RELEASE, latest))
        self.arguments[0] = self.arguments[0][:-extension_length]

        return LiteralInclude.run(self)

class VersionCodeBlock(CodeBlock):
    """
    Similar to CodeBlock but replaces a placeholder with the latest version of
    the Flocker CLI.

    Usage example:

    .. version-code-block:: console

       $ brew install flocker-|cli-release|
    """
    def run(self):
        parsed_version = parse_version(version)
        latest = parsed_version.client_release

        self.content = [item.replace(CLI_RELEASE, latest) for
                        item in self.content]
        return CodeBlock.run(self)


def setup(app):
    app.add_directive('version-code-block', VersionCodeBlock)
    app.add_directive('version-literalinclude', VersionLiteralInclude)
    app.add_role('version-download', VersionDownload())
