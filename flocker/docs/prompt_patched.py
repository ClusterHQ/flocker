#!/usr/bin/python
# coding: utf-8


from docutils import nodes
from docutils.parsers import rst

from pygments import highlight
from pygments.lexers import TextLexer
from pygments.lexers import BashLexer
from pygments.lexers import PythonLexer
from pygments.lexers import ScalaLexer
from pygments.formatters import HtmlFormatter


class PromptCache:

    def __init__(self):
        self.clear()

    def clear(self, *ignored):
        # ignored parameters allow this method to be used as event handler
        self.next_index = 1
        self.prompts = {}

    def register_prompt(self, prompt):
        if prompt in self.prompts:
            return ''
        else:
            index = self.next_index
            self.next_index = index + 1
            self.prompts[prompt] = index
            return """span.prompt%i:before {
  content: "%s ";
}
""" % (index, prompt)

    def get_prompt_class(self, prompt):
        return 'prompt%i' % self.prompts[prompt]


cache = PromptCache()


class PromptDirective(rst.Directive):

    optional_arguments = 3
    has_content = True

    def run(self):
        self.assert_has_content()

        language = 'text'
        prompt = None
        modifiers = []

        if self.arguments:
            language = self.arguments[0]
            if len(self.arguments) > 1:
                prompt = self.arguments[1]
            elif language == 'bash':
                prompt = '$'
            if len(self.arguments) > 2:
                modifiers = self.arguments[2].split(',')
            if 'auto' in modifiers:
                prompts = prompt.split(',')

        html = '<pre class="highlight">'
        styles = ''
        if 'auto' in modifiers:
            for prompt in prompts:
                styles += cache.register_prompt(prompt)
        else:
            if prompt is not None:
                styles += cache.register_prompt(prompt)
        if styles:
            html += '<style type="text/css">\n' + styles + '</style>'
        latex = "\\begin{Verbatim}[commandchars=\\\\\\{\\}]"

        Lexer = TextLexer
        if language == 'bash':
            Lexer = BashLexer
        elif language == 'python':
            Lexer = PythonLexer
        elif language == 'scala':
            Lexer = ScalaLexer

        statement = []
        if 'auto' in modifiers:
            prompt_class = ''
            for line in self.content:
                latex += '\n' + line

                for prompt in prompts:
                    if line.startswith(prompt):
                        if len(statement) > 0:
                            html += '<span class="%s">%s</span>\n' % (
                                prompt_class,
                                highlight(
                                    '\n'.join(statement),
                                    Lexer(),
                                    HtmlFormatter(nowrap=True)
                                ).strip('\r\n')
                            )
                            statement = []
                        line = line[len(prompt):].strip()
                        prompt_class = cache.get_prompt_class(prompt)
                        break

                statement.append(line)
            # Add last prompt
            if len(statement) > 0:
                html += '<span class="%s">%s</span>\n' % (
                    prompt_class,
                    highlight(
                        '\n'.join(statement),
                        Lexer(),
                        HtmlFormatter(nowrap=True)
                    ).strip('\r\n')
                )
        elif language == 'bash' or language == 'python':
            for line in self.content:
                statement.append(line)
                if len(line) == 0 or not line[-1] == '\\':
                    html += '<span class="%s">%s</span>\n' % (
                        cache.get_prompt_class(prompt),
                        highlight(
                            '\n'.join(statement),
                            Lexer(),
                            HtmlFormatter(nowrap=True)
                        ).strip('\r\n')
                    )
                    if prompt is not None:
                        latex += '\n%s %s' % (prompt, '\n'.join(statement))
                    else:
                        latex += '\n' + '\n'.join(statement)
                    statement = []
        else:
            for line in self.content:
                html += '<span class="%s">%s</span>\n' % (
                    cache.get_prompt_class(prompt),
                    highlight(
                        line,
                        Lexer(),
                        HtmlFormatter(nowrap=True)
                    ).strip('\r\n')
                )
                if prompt is not None:
                    latex += '\n%s %s' % (prompt, line)
                else:
                    latex += '\n' + line

        html += "</pre>"
        latex += "\n\\end{Verbatim}"

        return [
            nodes.raw('\n'.join(self.content), html, format="html"),
            nodes.raw('\n'.join(self.content), latex, format="latex"),
        ]


def setup(app):
    app.add_directive('prompt', PromptDirective)
    app.connect('env-purge-doc', cache.clear)
