
from textwrap import dedent
from docutils.parsers.rst import Directive

from docutils import nodes


class collapsepanel(nodes.General, nodes.Element):
    pass


def visit_collapsepanel_html(self, node):
    pass


def depart_collapsepanel_html(self, node):
    pass


class collapsecontent(nodes.General, nodes.Element):
    pass


def visit_collapsecontent_html(self, node):
    classes = ['collapse']
    self.body.append(dedent("""
    <div id="%(id)s" class="collapse">
    """ % {"classes": " ".join(classes), "id": node['ids'][0]}))


def depart_collapsecontent_html(self, node):
    self.body.append(dedent("""
    </div>
    """))


class collapselink(nodes.General, nodes.TextElement):
    pass


def visit_collapselink_html(self, node):
    self.body.append(dedent("""
    <button type="button" class="btn btn-danger" data-toggle="collapse" data-target="#%(id)s">
    """ % {"id": node['refid']}))


def depart_collapselink_html(self, node):
    self.body.append(dedent("""
    </button>
    """))


class CollapseDirective(Directive):
    """
    Implementation of the C{collapse} directive.
    """

    has_content = True

    def run(self):
        node = collapsepanel(tag='div')
        text = self.content
        self.state.nested_parse(text, self.content_offset, node,
                                match_titles=True)

        self.state.document.settings.record_dependencies.add(__file__)
        return [node]


def process_collapse_node(node):
    sections = node.children
    assert len(sections) == 1
    [section] = sections
    assert isinstance(section, nodes.section)
    assert isinstance(section.children[0], nodes.title)
    title = section.children[0]
    id = section['ids'][0]
    body = collapsecontent(section.rawsource, *section.children[1:],
                           ids=section['ids'], active=False)
    header = collapselink([], *title.children, refid=id, active=False)

    node.children = [header, body]


def process_collapse_nodes(app, doctree, fromdocname):
    for node in doctree.traverse(collapsepanel):
        process_collapse_node(node)


def setup(app):
    """
    Entry point for sphinx extension.
    """
    app.add_directive('collapse', CollapseDirective)
    app.add_node(
        collapsepanel,
        html=(visit_collapsepanel_html, depart_collapsepanel_html))
    app.add_node(
        collapsecontent,
        html=(visit_collapsecontent_html, depart_collapsecontent_html))
    app.add_node(
        collapselink,
        html=(visit_collapselink_html, depart_collapselink_html))
    app.connect('doctree-resolved', process_collapse_nodes)
