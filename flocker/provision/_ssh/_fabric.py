from fabric.api import settings, run, put, sudo
from fabric.network import disconnect_all
from StringIO import StringIO

from ._model import Run, Sudo, Put, Comment, RunRemotely

from effect import (
    sync_performer,
    sync_perform,
    TypeDispatcher, ComposedDispatcher,
    )


@sync_performer
def perform_run_remotely(base_dispatcher, intent):
    """
    Run a series of commands on a remote host.
    """

    dispatcher = ComposedDispatcher([
        TypeDispatcher({
            Run: lambda _, intent: run(intent.command),
            Sudo: lambda _, intent: sudo(intent.command),
            Put: lambda _, intent: put(StringIO(intent.content), intent.path),
            Comment: lambda _, intent: None,
        }),
        base_dispatcher,
    ])

    host_string = "%s@%s" % (intent.username, intent.address)
    with settings(
            connection_attempts=24,
            timeout=5,
            pty=False,
            host_string=host_string):

        sync_perform(dispatcher, intent.commands)

    disconnect_all()

dispatcher = TypeDispatcher({
    RunRemotely: perform_run_remotely,
})
