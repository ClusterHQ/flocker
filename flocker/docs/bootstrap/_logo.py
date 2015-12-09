
# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Logo directive
"""

from textwrap import dedent

from docutils import nodes
from docutils.parsers.rst import Directive


class logo(nodes.General, nodes.Element):
    pass


def visit_html_logo(self, node):
    self.body.append(dedent("""\
    <div class="flocker-logo pull-right"></div>
    """))


def depart_html_logo(self, node):
    pass


class LogoDirective(Directive):
    """
    Implementation of the C{tabs} directive.
    """

    has_content = False

    def run(self):
        node = logo()
        text = self.content
        self.state.nested_parse(text, self.content_offset, node,
                                match_titles=True)

        self.state.document.settings.record_dependencies.add(__file__)
        return [node]


def setup(app):
    """
    Entry point for sphinx extension.
    """
    app.add_node(logo,
                 html=(visit_html_logo, depart_html_logo))
    app.add_directive('logo', LogoDirective)
