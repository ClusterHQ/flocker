# Copyright ClusterHQ Inc.  See LICENSE file for details.
# Portions Copyright 2007-2014 by the Sphinx team.
# Sphinx released under the BSD license
# Portions taken from Docutils, http://docutils.sourceforge.net/
# Docutils is public domain, http://docutils.sourceforge.net/COPYING.html

"""
Bootstrap extension entry point.
"""

from docutils import nodes
from sphinx.writers.html import HTMLTranslator
from . import _simple, _tabs


def setup(app):
    """
    Entry point for sphinx extension.
    """

    for module in [_simple, _tabs]:
        module.setup(app)


class HTMLWriter(HTMLTranslator):
    """
    Overrides part of the default HTMLTranslator to provide specific
    class names on some generated HTML elements.

    Code modified from docutils.writers.html4css1.Writer and
    sphinx.writers.html.HTMLTranslator

    http://sphinx-doc.org/
    http://docutils.sourceforge.net/
    """

    def visit_table(self, node):
        """
        Modified version of sphinx.writers.html.HTMLTranslator.visit_table
        and including code from docutils.writers.html4css1.Writer.visit_table
        Adds additional class names to <table> tags.
        """
        self._table_row_index = 0
        self.context.append(self.compact_p)
        self.compact_p = True
        classes = ' '.join(['docutils', 'table', 'table-striped',
                            self.settings.table_style]).strip()
        self.body.append(
            self.starttag(node, 'table', CLASS=classes, border="0"))

    def visit_entry(self, node):
        """
        Modified version of docutils.writers.html4css1.Writer.visit_entry
        Adds a wrapping <p> tag to table cell content.
        """
        atts = {'class': []}
        if isinstance(node.parent.parent, nodes.thead):
            atts['class'].append('head')
        if node.parent.parent.parent.stubs[node.parent.column]:
            # "stubs" list is an attribute of the tgroup element
            atts['class'].append('stub')
        if atts['class']:
            tagname = 'th'
            atts['class'] = ' '.join(atts['class'])
        else:
            tagname = 'td'
            del atts['class']
        node.parent.column += 1
        if 'morerows' in node:
            atts['rowspan'] = node['morerows'] + 1
        if 'morecols' in node:
            atts['colspan'] = node['morecols'] + 1
            node.parent.column += node['morecols']
        self.body.append(self.starttag(node, tagname, '', **atts))
        self.body.append(self.starttag(node, 'p', '', dict()))
        self.context.append('</p></%s>\n' % tagname.lower())
        if len(node) == 0:              # empty cell
            self.body.append('&nbsp;')
        self.set_first_last(node)
