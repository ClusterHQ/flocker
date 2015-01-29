# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Sphinx extension to add a ``task`` directive

This directive allows sharing code between documentation and provisioning code.

.. code-block:: rest

   .. task:: name_of_task

``name_of_task`` must the name of a task in ``flocker.provision._tasks``,
without the ``task_`` prefix. A task must take a single runner argument.
"""

from inspect import getsourcefile
from docutils.parsers.rst import Directive
from docutils import nodes
from docutils.statemachine import StringList

from . import _tasks as tasks
from ._install import Run, Sudo, Comment

from flocker import __version__ as version

def run(command):
    return [command.command]


def sudo(command):
    return ["sudo %s" % (command.command,)]


def comment(command):
    return ["# %s" % (command.comment)]


HANDLERS = {
    Run: run,
    Sudo: sudo,
    Comment: comment,
}


from docutils.parsers.rst import directives
from docutils.parsers.rst.roles import set_classes
from docutils.utils.code_analyzer import Lexer, LexerError, NumberLines
# from sphinx.directives.code import CodeBlock
from sphinx import addnodes
from sphinx.util import parselinenos
from sphinx.util.nodes import set_source_info
class FooDirective(Directive):
    """
    Like code-block but replaces |release|.
    """
    has_content = True
    required_arguments = 1
    optional_arguments = 0
    final_argument_whitespace = False
    option_spec = {
        'linenos': directives.flag,
        'emphasize-lines': directives.unchanged_required,
    }

    def run(self):
        code = u'\n'.join(self.content)
        # Use the WIP function to get the latest release version
        release_to_replace = u'|release|'
        code = code.replace(release_to_replace, version)

        linespec = self.options.get('emphasize-lines')
        if linespec:
            try:
                nlines = len(self.content)
                hl_lines = [x+1 for x in parselinenos(linespec, nlines)]
            except ValueError, err:
                document = self.state.document
                return [document.reporter.warning(str(err), line=self.lineno)]
        else:
            hl_lines = None

        literal = nodes.literal_block(code, code)
        literal['language'] = self.arguments[0]
        literal['linenos'] = 'linenos' in self.options
        if hl_lines is not None:
            literal['highlight_args'] = {'hl_lines': hl_lines}
        set_source_info(self, literal)
        return [literal]


class TaskDirective(Directive):
    """
    Implementation of the C{task} directive.
    """
    required_arguments = 1

    option_spec = {
        'prompt': str
    }

    def run(self):
        task = getattr(tasks, 'task_%s' % (self.arguments[0],))
        prompt = self.options.get('prompt', '$')

        commands = task()
        lines = ['.. prompt:: bash %s' % (prompt,), '']

        for command in commands:
            try:
                handler = HANDLERS[type(command)]
            except KeyError:
                raise self.error("task: %s not supported"
                                 % (type(command).__name__,))
            lines += ['   %s' % (line,) for line in handler(command)]

        # The following three lines record (some?) of the dependencies of the
        # directive, so automatic regeneration happens.  Specifically, it
        # records this file, and the file where the task is declared.
        task_file = getsourcefile(task)
        tasks_file = getsourcefile(tasks)
        self.state.document.settings.record_dependencies.add(task_file)
        self.state.document.settings.record_dependencies.add(tasks_file)
        self.state.document.settings.record_dependencies.add(__file__)

        node = nodes.Element()
        text = StringList(lines)
        self.state.nested_parse(text, self.content_offset, node)
        return node.children


def setup(app):
    """
    Entry point for sphinx extension.
    """
    app.add_directive('task', TaskDirective)
    app.add_directive('foo', FooDirective)

