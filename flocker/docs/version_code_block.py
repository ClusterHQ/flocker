# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Sphinx extension to add a ``version-code-block`` directive.

This directive allows Flocker's release version to be inserted into code
blocks.

.. version-code-block:: console

   $ brew install flocker-|latest-packaged-version|
"""

from sphinx.directives.code import CodeBlock

from flocker import __version__ as version
from flocker.docs import parse_version


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
        block = CodeBlock(self.name, self.arguments, self.options,
                          self.content, self.lineno, self.content_offset,
                          self.block_text, self.state, self.state_machine)
        return block.run()


def setup(app):
    app.add_directive('version-code-block', VersionCodeBlock)
