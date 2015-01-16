# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Jumbotron directive
"""

from textwrap import dedent

from docutils import nodes
from docutils.parsers.rst import Directive


class jumbotron(nodes.General, nodes.Element):
    pass


def visit_html_jumbotron(self, node):
    self.body.append(dedent("""\
    <div class="jumbotron jumbo-flocker">
      <div class="container">
        <div class="row">
          <div class="col-md-9">
    """))


def depart_html_jumbotron(self, node):
    self.body.append(dedent("""\
          </div>
        </div>
      </div>
    </div>
    """))


class JumbotronDirective(Directive):
    """
    Implementation of the C{tabs} directive.
    """

    has_content = True

    def run(self):
        node = jumbotron()
        text = self.content
        self.state.nested_parse(text, self.content_offset, node,
                                match_titles=True)

        self.state.document.settings.record_dependencies.add(__file__)
        return [node]


def setup(app):
    """
    Entry point for sphinx extension.
    """
    app.add_node(jumbotron,
                 html=(visit_html_jumbotron, depart_html_jumbotron))
    app.add_directive('jumbotron', JumbotronDirective)
