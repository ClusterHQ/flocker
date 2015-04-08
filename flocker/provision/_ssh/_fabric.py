from fabric.api import settings, run, put, sudo
from fabric.network import disconnect_all
from StringIO import StringIO

from ._model import Run, Sudo, Put, Comment, RunRemotely

from effect import (
    sync_performer,
    sync_perform,
    TypeDispatcher, ComposedDispatcher,
    )

from .._effect import dispatcher as base_dispatcher


@sync_performer
def perform_run(dispatcher, intent):
    run(intent.command),


@sync_performer
def perform_sudo(dispatcher, intent):
    sudo(intent.command),


@sync_performer
def perform_put(dispatcher, intent):
    put(StringIO(intent.content), intent.path),


@sync_performer
def perform_comment(dispatcher, intent):
    pass


@sync_performer
def perform_run_remotely(base_dispatcher, intent):
    """
    Run a series of commands on a remote host.
    """

    dispatcher = ComposedDispatcher([
        TypeDispatcher({
            Run: perform_run,
            Sudo: perform_sudo,
            Put: perform_put,
            Comment: perform_comment,
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

dispatcher = ComposedDispatcher([
    TypeDispatcher({
        RunRemotely: perform_run_remotely,
    }),
    base_dispatcher,
])
