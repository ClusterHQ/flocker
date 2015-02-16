"""Simple, inelegant Sphinx extension which adds a directive for a
highlighted code-block that may be toggled hidden and shown in HTML.  
This is possibly useful for teaching courses.

The directive, like the standard code-block directive, takes
a language argument and an optional linenos parameter.  The
hidden-code-block adds starthidden and label as optional 
parameters.

Examples:

.. hidden-code-block:: python
    :starthidden: False

    a = 10
    b = a + 5

.. hidden-code-block:: python
    :label: --- SHOW/HIDE ---

    x = 10
    y = x + 5

Thanks to http://www.javascriptkit.com/javatutors/dom3.shtml for 
inspiration on the javascript.  

Thanks to Milad 'animal' Fatenejad for suggesting this extension 
in the first place.

Written by Anthony 'el Scopz' Scopatz, January 2012.

Released under the WTFPL (http://sam.zoy.org/wtfpl/).
"""

from docutils import nodes
from docutils.parsers.rst import directives
from sphinx.directives.code import CodeBlock

HCB_COUNTER = 0

js_showhide = """\
<script type="text/javascript">
    function showhide(element){
        if (!document.getElementById)
            return

        if (element.style.display == "block")
            element.style.display = "none"
        else
            element.style.display = "block"
    };
</script>
"""

def nice_bool(arg):
    tvalues = ('true',  't', 'yes', 'y')
    fvalues = ('false', 'f', 'no',  'n')
    arg = directives.choice(arg, tvalues + fvalues)
    return arg in tvalues


class hidden_code_block(nodes.General, nodes.FixedTextElement):
    pass


class HiddenCodeBlock(CodeBlock):
    """Hidden code block is Hidden"""

    option_spec = dict(starthidden=nice_bool, 
                       label=str,
                       **CodeBlock.option_spec)

    def run(self):
        # Body of the method is more or less copied from CodeBlock
        code = u'\n'.join(self.content)
        hcb = hidden_code_block(code, code)
        hcb['language'] = self.arguments[0]
        hcb['linenos'] = 'linenos' in self.options
        hcb['starthidden'] = self.options.get('starthidden', True)
        hcb['label'] = self.options.get('label', '+ show/hide code')
        hcb.line = self.lineno
        return [hcb]


def visit_hcb_html(self, node):
    """Visit hidden code block"""
    global HCB_COUNTER
    HCB_COUNTER += 1

    # We want to use the original highlighter so that we don't
    # have to reimplement it.  However it raises a SkipNode 
    # error at the end of the function call.  Thus we intercept
    # it and raise it again later.
    try: 
        self.visit_literal_block(node)
    except nodes.SkipNode:
        pass

    # The last element of the body should be the literal code 
    # block that was just made.
    code_block = self.body[-1]

    fill_header = {'divname': 'hiddencodeblock{0}'.format(HCB_COUNTER), 
                   'startdisplay': 'none' if node['starthidden'] else 'block', 
                   'label': node.get('label'), 
                   }

    divheader = ("""<p><strong><a href="javascript:showhide(document.getElementById('{divname}'))">"""
                 """{label}</a></strong></p>"""
                 '''<div id="{divname}" style="display: {startdisplay}">'''
                 ).format(**fill_header)

    code_block = js_showhide + divheader + code_block + "</div>"

    # reassign and exit
    self.body[-1] = code_block
    raise nodes.SkipNode


def depart_hcb_html(self, node):
    """Depart hidden code block"""
    # Stub because of SkipNode in visit


def visit_hcb_latex(self, node):
    pass


def depart_hcb_latex(self, node):
    pass


def setup(app):
    app.add_directive('hidden-code-block', HiddenCodeBlock)
    app.add_node(hidden_code_block,
            html=(visit_hcb_html, depart_hcb_html),
            latex=(visit_hcb_latex, depart_hcb_latex))
