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
from ._install import Run, Sudo, Comment, Put


def run(command):
    return command.command


def sudo(command):
    return "sudo %s" % (command.command,)


def comment(command):
    return "# %s" % (command.comment)


def put(command):
    return [
        "cat <<EOF > %s" % (command.path,),
    ] + command.content.splitlines() + [
        "EOF",
    ]


HANDLERS = {
    Run: run,
    Sudo: sudo,
    Comment: comment,
    Put: put,
}


class TaskDirective(Directive):
    """
    Implementation of the C{task} directive.
    """
    required_arguments = 1
    optional_arguments = 1
    final_argument_whitespace = True

    option_spec = {
        'prompt': str
    }

    def run(self):
        task = getattr(tasks, 'task_%s' % (self.arguments[0],))
        prompt = self.options.get('prompt', '$')
        if len(self.arguments) > 1:
            task_arguments = self.arguments[1].split()
        else:
            task_arguments = []

        commands = task(*task_arguments)
        lines = ['.. prompt:: bash %s,> auto' % (prompt,), '']

        for command in commands:
            try:
                handler = HANDLERS[type(command)]
            except KeyError:
                raise self.error("task: %s not supported"
                                 % (type(command).__name__,))
            # handler can return either a string or a list.  If it is a string,
            # treat the elements after the first as continuation lines.
            command_line = handler(command)
            if isinstance(command_line, list):
                lines.append('   %s %s' % (prompt, command_line[0],))
                lines.extend(['   > %s' % (line,)
                              for line in command_line[1:]])
            else:
                lines.append('   %s %s' % (prompt, command_line,))

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
