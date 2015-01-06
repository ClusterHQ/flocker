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
from ._install import Run


class DocRunner(object):
    """
    Task runner that records the executed commands.
    """
    def __init__(self):
        self.commands = []

    def run(self, command):
        self.commands.extend(command.splitlines())

    def put(self, content, path):
        raise NotImplementedError("put not supported.")


class TaskDirective(Directive):
    """
    Implementation of the C{task} directive.
    """
    required_arguments = 1

    def run(self):
        task = getattr(tasks, 'task_%s' % (self.arguments[0],))

        commands = task()
        lines = ['.. prompt:: bash $', '']

        for command in commands:
            if type(command) != Run:
                raise self.error("task: %s not supported"
                                 % (type(command).__name__,))
            lines += ['   %s' % (command.command,)]

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
