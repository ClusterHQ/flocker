
# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Columns directive
"""

from textwrap import dedent

from docutils import nodes
from docutils.parsers.rst import Directive


def create_simple_html_directive(name, pre, post, has_content=True):

    node_class = type(name, (nodes.General, nodes.Element), {})

    def visit_html(self, node):
        self.body.append(pre)

    def depart_html(self, node):
        self.body.append(post)

    def run_directive(self):
        node = node_class()
        if has_content:
            text = self.content
            self.state.nested_parse(text, self.content_offset, node)
        # FIXME: This should add more stuff.
        self.state.document.settings.record_dependencies.add(__file__)
        return [node]

    directive_class = type(name.title() + 'Directive', (Directive,), {
        "has_content": has_content,
        "run": run_directive,
    })

    def setup(app):
        app.add_node(node_class,
                     html=(visit_html, depart_html))
        app.add_directive(name, directive_class)

    return node_class, directive_class, setup


columns, ColumnsDirective, columns_setup = create_simple_html_directive(
    "columns",
    pre=dedent("""\
    <div class="row">
    """),
    post=dedent("""\
    </div>
    """),
)

column, ColumnDirective, column_setup = create_simple_html_directive(
    "column",
    pre=dedent("""\
    <div class="col-md-6 bordered bordered-right bordered-bottom bordered-gray">
    """),
    post=dedent("""\
    </div>
    """),
)


def setup(app):
    """
    Entry point for sphinx extension.
    """
    columns_setup(app)
    column_setup(app)
