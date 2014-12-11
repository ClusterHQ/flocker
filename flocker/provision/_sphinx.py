# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

from inspect import getsourcefile
from docutils.parsers.rst import Directive
from docutils import nodes
from docutils.statemachine import StringList

from twisted.python.reflect import namedAny


class FakeRunner(object):
    def __init__(self):
        self.commands = []

    def run(self, command):
        self.commands.extend(command.splitlines())

    def put(self, content, path):
        raise NotImplementedError("put not supported.")


class TaskDirective(Directive):
    """
    Implementation of the C{frameimage} directive.
    """
    required_arguments = 1

    def run(self):
        task = namedAny(self.arguments[0])

        runner = FakeRunner()
        try:
            task(runner)
        except NotImplementedError as e:
            raise self.error("task: %s" % (e.args[0],))

        lines = ['.. code-block:: bash', '']
        lines += ['   %s' % (command,) for command in runner.commands]

        # The following three lines record (some?) of the dependencies of the
        # directive, so automatic regeneration happens.  Specifically, it
        # records this file, and the file where the task is declared.
        task_file = getsourcefile(task)
        self.state.document.settings.record_dependencies.add(task_file)
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
