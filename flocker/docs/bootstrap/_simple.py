
# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Simple directives that just wrap content.
"""

from textwrap import dedent

from docutils import nodes
from docutils.parsers.rst import directives
from docutils.parsers.rst import Directive


class EmptyDiv(Directive):
    """
    Creates a new directive that takes class names as arguments and when
    parsed to HTML, wraps those class names in an empty div.
    """
    has_content = False
    required_arguments = 1
    final_argument_whitespace = 1

    def run(self):
        html = '<div class="{meta}"></div>'.format(meta=self.arguments[0])
        return [nodes.raw('', html, format='html')]


def create_simple_html_directive(name, pre, post,
                                 has_content=True, match_titles=False):
    """
    Creates a node class, directive class and setup method for the given
    parameters.

    :param name: String representing the RST directive to add.
    :param pre: String representing HTML to come before directive content.
    :param post: String representing HTML to come after directive content.
    :param has_content: Boolean indicating whether the directive accepts
        a content block.
    :param match_titles: Boolean indicating whether headings and titles may
        be included in the block contained within this directive.
    """
    node_class = type(
        name.replace('-', '_'), (nodes.General, nodes.Element), {}
    )

    def visit_html(self, node):
        self.body.append(pre)

    def depart_html(self, node):
        self.body.append(post)

    def run_directive(self):
        node = node_class()
        if has_content:
            text = self.content
            self.state.nested_parse(text, self.content_offset,
                                    node, match_titles=match_titles)
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


intro_text, IntroTextDirective, intro_text_setup = (
    create_simple_html_directive(
        "intro-text",
        pre=dedent("""\
        <div class="jumbotron jumbo-flocker">
        <div class="container"><div class="row">
        <div class="col-md-9"><p>
        """),
        post=dedent("""\
        </p></div></div></div></div>
        """),
    ))


tutorial_step_condensed, TutorialStepCondensedDirective, \
    tutorial_step_condensed_setup = (
        create_simple_html_directive(
            "tutorial-step-condensed",
            pre=dedent("""\
            <div class="row row-centered"><div class="\
    col-md-9 col-sm-12 col-xs-12 col-centered">
            """),
            post=dedent("""\
            </div></div>
            """),
            match_titles=True,
        ))


tutorial_step, TutorialStepDirective, tutorial_step_setup = (
    create_simple_html_directive(
        "tutorial-step",
        pre=dedent("""\
        <div class="container"><div class="row"><div class="\
col-md-12 text-larger">
        """),
        post=dedent("""\
        </div></div></div>
        """),
        match_titles=True,
    ))


noscript_content, NoScriptContentDirective, noscript_content_setup = (
    create_simple_html_directive(
        "noscript-content",
        pre=dedent("""\
        <noscript>
        """),
        post=dedent("""\
        </noscript>
        """),
        match_titles=True,
    ))


mobile_label, MobileLabelDirective, mobile_label_setup = (
    create_simple_html_directive(
        "mobile-label",
        pre=dedent("""\
        <p class="hidden-sm hidden-md hidden-lg center-block \
flocker-orange flocker-label">
        """),
        post=dedent("""\
        </p>
        """),
    ))


parallel, ParallelDirective, parallel_setup = (
    create_simple_html_directive(
        "parallel",
        pre=dedent("""\
        <div class="col-md-6 bordered bordered-right \
bordered-bottom bordered-gray">
        """),
        post=dedent("""\
        </div>
        """),
        match_titles=True,
    ))


logo, LogoDirective, logo_setup = (
    create_simple_html_directive(
        "logo",
        pre=dedent("""\
        <div class="flocker-logo pull-right">
        """),
        post=dedent("""\
        </div>
        """),
        has_content=False,
    ))


def setup(app):
    """
    Entry point for sphinx extension.
    """
    directives.register_directive('empty-div', EmptyDiv)
    intro_text_setup(app)
    noscript_content_setup(app)
    tutorial_step_condensed_setup(app)
    tutorial_step_setup(app)
    mobile_label_setup(app)
    parallel_setup(app)
    logo_setup(app)
