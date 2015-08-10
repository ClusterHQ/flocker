# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for the flocker-diagnostics.
"""
from twisted.trial.unittest import TestCase

from ...testtools import loop_until

from ..testtools import (
    require_cluster, require_moving_backend, create_dataset,
    REALISTIC_BLOCKDEVICE_SIZE,
)


class DiagnosticsTests(TestCase):
    """
    Tests for ``flocker-diagnostics``.
    """
    # @require_cluster(1)
    def test_export(self):
        """
        ``flocker-diagnostics`` creates an archive of all Flocker service logs
        and server diagnostics information.
        """
        from twisted.internet import reactor
        from effect.twisted import perform
        from flocker.provision._ssh._conch import make_dispatcher
        from flocker.provision._ssh._model import run_remotely, run_from_args
        dispatcher = make_dispatcher(reactor)
        remote_command = run_remotely(
            username='root',
            address='119.9.110.111',
            commands=run_from_args(['date']),
        )
        running = perform(dispatcher, remote_command)

        def verify(result):
            import pdb; pdb.set_trace()


        running.addBoth(verify)
        return running
