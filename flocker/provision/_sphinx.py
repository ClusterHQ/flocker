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
from docutils.parsers.rst.directives.body import CodeBlock
class FooDirective(CodeBlock):
    """
    Like code-block but replaces |release|.
    """
    def run(self):
        replacement = '0.3.5'
        release_to_replace = u'|release|'
        self.content = [item.replace(release_to_replace, replacement) for item in self.content]
        return CodeBlock.run(self)

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

