# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Bootstrap extension entry point.
"""

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
    """
    
    def visit_table(self, node):
        self._table_row_index = 0
        self.context.append(self.compact_p)
        self.compact_p = True
        classes = ' '.join(['docutils', 'table', 'table-striped',
                            self.settings.table_style]).strip()
        self.body.append(
            self.starttag(node, 'table', CLASS=classes, border="0"))
    
