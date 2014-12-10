from docutils.parsers.rst import Directive
from twisted.python.reflect import namedAny
from docutils import nodes
from docutils.statemachine import StringList
from docutils.parsers.rst import directives


class FakeRunner(object):
    def __init__(self):
        self.commands = []

    def run(self, command):
        self.commands.extend(command.splitlines())


class TaskDirective(Directive):
    """
    Implementation of the C{frameimage} directive.
    """
    required_arguments = 1

    option_spec = {'prompt': directives.unchanged}

    def run(self):
        prompt = self.options.get('prompt', '$')
        task = self.arguments[0]

        from flocker.provision import _install
        fake = FakeRunner()
        _install.run = fake.run
        namedAny(task)()
        lines = ['.. code-block:: console', '']
        lines += ['   %s %s' % (prompt, command) for command in fake.commands]
        node = nodes.Element()
        text = StringList(lines)
        self.state.nested_parse(text, self.content_offset, node)
        return node.children


def setup(app):
    """
    Entry point for sphinx extension.
    """
    app.add_directive('task', TaskDirective)
