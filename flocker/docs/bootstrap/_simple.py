
# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Simple directives that just wrap content.
"""

from textwrap import dedent

from docutils import nodes
from docutils.parsers.rst import directives
from docutils.parsers.rst import Directive


def parse_general_division(
    name, arguments, options, content, lineno,
    content_offset, block_text, state, state_machine
):
    if 'meta' not in options:
        options['meta'] = ''
    html = '<div class="{meta}"></div>'.format(meta=options['meta'])

    return [nodes.raw('', html, format='html')]


def create_simple_html_directive(name, pre, post,
                                 has_content=True, match_titles=False):

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


header_hero, HeaderHeroDirective, header_hero_setup = (
    create_simple_html_directive(
        "header-hero",
        pre=dedent("""\
        <header><h1 class="text-center">
        """),
        post=dedent("""\
        </h1></header>
        """),
    ))

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
    parse_general_division.content = False
    parse_general_division.arguments = (0, 0, False)
    parse_general_division.options = dict(meta=directives.unchanged)
    directives.register_directive('general-division', parse_general_division)
    intro_text_setup(app)
    header_hero_setup(app)
    tutorial_step_condensed_setup(app)
    tutorial_step_setup(app)
    mobile_label_setup(app)
    parallel_setup(app)
    logo_setup(app)
