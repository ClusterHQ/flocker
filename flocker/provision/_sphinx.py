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
class FooDirective(Directive):
    """
    Implementation of the C{task} directive.
    """
    optional_arguments = 1
    option_spec = {'class': directives.class_option,
                   'name': directives.unchanged,
                   'number-lines': directives.unchanged # integer or None
                  }
    has_content = True

    def run(self):
        self.assert_has_content()

        replacement = 'HERE IS RELEASE'
        self.content = [replacement if u'|release|' in item else item for item in self.content]

        if self.arguments:
            language = self.arguments[0]
        else:
            language = ''
        set_classes(self.options)
        classes = ['code']
        if language:
            classes.append(language)
        if 'classes' in self.options:
            classes.extend(self.options['classes'])

        # set up lexical analyzer
        try:
            tokens = Lexer(u'\n'.join(self.content), language,
                           self.state.document.settings.syntax_highlight)
        except LexerError, error:
            raise self.warning(error)

        if 'number-lines' in self.options:
            # optional argument `startline`, defaults to 1
            try:
                startline = int(self.options['number-lines'] or 1)
            except ValueError:
                raise self.error(':number-lines: with non-integer start value')
            endline = startline + len(self.content)
            # add linenumber filter:
            tokens = NumberLines(tokens, startline, endline)

        node = nodes.literal_block('\n'.join(self.content), classes=classes)
        self.add_name(node)

        # if called from "include", set the source
        if 'source' in self.options:
            node.attributes['source'] = self.options['source']
        # analyze content and add nodes for every token
        for classes, value in tokens:
            # print (classes, value)
            if classes:
                node += nodes.inline(value, value, classes=classes)
            else:
                # insert as Text to decrease the verbosity of the output
                node += nodes.Text(value, value)

        return [node]

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

