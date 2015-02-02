# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Sphinx extension to add a ``version-code-block`` directive.

This directive allows Flocker's release version to be inserted into code
blocks.

.. version-code-block:: console

   $ brew install flocker-|latest-packaged-version|
"""

from sphinx.directives.code import CodeBlock, LiteralInclude
from sphinx.roles import XRefRole

from flocker import __version__ as version
from flocker.docs import parse_version

from sphinx import addnodes
from sphinx.util import ws_re
class VersionRole(XRefRole):
    """docstring for VersionRole"""
    nodeclass = addnodes.download_reference
    def process_link(self, env, refnode, has_explicit_title, title, target):
        rel_filename, filename = env.relfn2path(target)
        extension_length = len('.template')
        with open(rel_filename, 'r') as templated_file:
            with open(rel_filename[:-extension_length], 'w') as new_file:
                new_file.write(templated_file.read().replace('Python', 'HELLO ADAM'))
        return title[:-extension_length], ws_re.sub(' ', target[:-extension_length])


class VersionLiteralInclude(LiteralInclude):
    """
    Similar to LiteralInclude but replaces |latest-packaged-version| with the latest
    packaged version of Flocker.

    # TODO same with download
    # TODO remove linux-install.sh and other templated files
    # Rename this file / change comment to version_directives
    """
    def run(self):
        document = self.state.document
        env = document.settings.env
        extension_length = len('.template')
        rel_filename, filename = env.relfn2path(self.arguments[0])
        with open(rel_filename, 'r') as templated_file:
            with open(rel_filename[:-extension_length], 'w') as new_file:
                new_file.write(templated_file.read().replace('Python', 'HELLO ADAM'))
        self.arguments[0] = self.arguments[0][:-extension_length]

        return LiteralInclude.run(self)

class VersionCodeBlock(CodeBlock):
    """
    Similar to CodeBlock but replaces |latest-packaged-version| with the latest
    packaged version of Flocker.
    """
    def run(self):
        parsed_version = parse_version(version)
        latest = parsed_version.release

        if parsed_version.weekly_release is not None:
            latest = latest + 'dev' + parsed_version.weekly_release
        elif parsed_version.pre_release is not None:
            latest = latest + 'pre' + parsed_version.pre_release

        self.content = [item.replace(u'|latest-packaged-version|', latest) for
                        item in self.content]
        return CodeBlock.run(self)


def setup(app):
    app.add_directive('version-code-block', VersionCodeBlock)
    app.add_directive('version-literalinclude', VersionLiteralInclude)
    app.add_role('version-download', VersionRole())
