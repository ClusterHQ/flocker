# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Sphinx extension to add a ``version-code-block`` directive

This directive allows Flocker's release version to be inserted into code
blocks.

.. version-code-block:: console

   $ brew install flocker-|RELEASE|
"""

from sphinx.directives.code import CodeBlock

from flocker import __version__ as version


class VersionCodeBlock(CodeBlock):
    """
    Similar to CodeBlock but replaces |RELEASE| with the latest release
    version.
    """
    def run(self):
        # Use the WIP get_doc_version to get the latest release version
        # from https://github.com/ClusterHQ/flocker/pull/1092/
        self.content = [item.replace(u'|RELEASE|', version) for item in
                        self.content]
        block = CodeBlock(self.name, self.arguments, self.options,
                          self.content, self.lineno, self.content_offset,
                          self.block_text, self.state, self.state_machine)
        return block.run()


def setup(app):
    app.add_directive('version-code-block', VersionCodeBlock)
