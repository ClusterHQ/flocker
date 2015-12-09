# Copyright ClusterHQ Inc.  See LICENSE file for details.

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

from flocker import __version__ as version

from flocker.common.version import get_installable_version
from flocker.docs.version_extensions import PLACEHOLDER

from . import _tasks as tasks
from ._ssh import Run, Sudo, Comment, Put
from ._effect import dispatcher as base_dispatcher, SequenceFailed
from effect import (
    sync_perform, sync_performer,
    ComposedDispatcher, TypeDispatcher,
    NoPerformerFoundError,
)


def run_for_docs(effect):

    commands = []

    @sync_performer
    def run(dispatcher, intent):
        commands.append(intent.command)

    @sync_performer
    def sudo(dispatcher, intent):
        commands.append("sudo %s" % (intent.command,))

    @sync_performer
    def comment(dispatcher, intent):
        commands.append("# %s" % (intent.comment))

    @sync_performer
    def put(dispatcher, intent):
        commands.append([
            "cat <<EOF > %s" % (intent.path,),
        ] + intent.content.splitlines() + [
            "EOF",
        ])

    sync_perform(
        ComposedDispatcher([
            TypeDispatcher({
                Run: run,
                Sudo: sudo,
                Comment: comment,
                Put: put,
            }),
            base_dispatcher,
        ]),
        effect,
    )

    return commands


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
            # Some tasks can include the latest installable version as (part
            # of) an argument. This replaces a placeholder with that version.
            arguments = self.arguments[1].split()
            latest = get_installable_version(version)
            task_arguments = [item.replace(PLACEHOLDER, latest).encode("utf-8")
                              for item in arguments]
        else:
            task_arguments = []

        commands = task(*task_arguments)
        lines = ['.. prompt:: bash %s,> auto' % (prompt,), '']

        try:
            command_lines = run_for_docs(commands)
        except NoPerformerFoundError as e:
            raise self.error("task: %s not supported"
                             % (type(e.args[0]).__name__,))
        except SequenceFailed as e:
            print e.error

        for command_line in command_lines:
            # handler can return either a string or a list.  If it returns a
            # list, treat the elements after the first as continuation lines.
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
