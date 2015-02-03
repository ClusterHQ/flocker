from textwrap import dedent
from docutils.parsers.rst import Directive

from docutils import nodes


class tabpanel(nodes.General, nodes.Element):
    pass


def visit_tabpanel_html(self, node):
    pass


def depart_tabpanel_html(self, node):
    pass


class tabcontent(nodes.General, nodes.Element):
    pass


def visit_tabcontent_html(self, node):
    self.body.append(dedent("""
    <div class="tab-content">
    """))


def depart_tabcontent_html(self, node):
    self.body.append(dedent("""
    </div>
    """))


class tab(nodes.General, nodes.Element):
    pass


def visit_tab_html(self, node):
    classes = ['tab-pane']
    if node['active']:
        classes.append("active")
    self.body.append(dedent("""
    <div class="%(classes)s" id="li-%(id)s">
    """ % {"classes": " ".join(classes), "id": node['ids'][0]}))


def depart_tab_html(self, node):
    self.body.append(dedent("""
    </div>
    """))


class tablink(nodes.General, nodes.Element):
    pass


def visit_tablink_html(self, node):
    if node['active']:
        active = 'class="active"'
    else:
        active = ''
    self.body.append(dedent("""
    <li %(active)s><a href="#li-%(id)s" data-toggle="tab">
    """ % {"active": active, "id": node['refid']}))


def depart_tablink_html(self, node):
    self.body.append(dedent("""
    </a></li>
    """))


class tablist(nodes.General, nodes.Element):
    pass


def visit_tablist_html(self, node):
    self.body.append(dedent("""
    <ul class="nav nav-tabs" data-tabs="tabs">
    """))


def depart_tablist_html(self, node):
    self.body.append(dedent("""
    </ul>
    """))


class TabsDirective(Directive):
    """
    Implementation of the C{tabs} directive.
    """

    has_content = True

    def run(self):
        node = tabpanel(attributes={"role": "tabpanel"}, tag='div')
        text = self.content
        self.state.nested_parse(text, self.content_offset, node,
                                match_titles=True)

        self.state.document.settings.record_dependencies.add(__file__)
        return [node]


def process_tab_node(node):
    tab_sections = node.children
    tabs = []
    headers = []
    for child in tab_sections:
        assert isinstance(child, nodes.section)
        assert isinstance(child.children[0], nodes.title)
        title = child.children[0]
        id = child['ids'][0]
        new_tab = tab(child.rawsource, *child.children[1:],
                      ids=child['ids'], active=False)
        tabs.append(new_tab)
        header = tablink([], *title.children, refid=id, active=False)
        headers.append(header)
    tabs[0]['active'] = True
    headers[0]['active'] = True

    node.children = [
        tablist([], *headers),
        tabcontent([], *tabs)
    ]


def process_tab_nodes(app, doctree, fromdocname):
    for node in doctree.traverse(tabpanel):
        process_tab_node(node)


def setup(app):
    """
    Entry point for sphinx extension.
    """
    app.add_directive('tabs', TabsDirective)
    app.add_node(tabpanel,
                 html=(visit_tabpanel_html, depart_tabpanel_html))
    app.add_node(tabcontent,
                 html=(visit_tabcontent_html, depart_tabcontent_html))
    app.add_node(tab,
                 html=(visit_tab_html, depart_tab_html))
    app.add_node(tablink,
                 html=(visit_tablink_html, depart_tablink_html))
    app.add_node(tablist,
                 html=(visit_tablist_html, depart_tablist_html))
    app.connect('doctree-resolved', process_tab_nodes)
