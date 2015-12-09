# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for the datasets REST API.
"""
import os

from datetime import timedelta
from uuid import UUID

from eliot import write_failure
from effect import parallel
from testtools import run_test_with
from twisted.internet import reactor
from twisted.trial.unittest import SkipTest
from txeffect import perform


from flocker import __version__ as version
from flocker.common.version import get_installable_version
from ...common import loop_until
from ...testtools import AsyncTestCase, async_runner, flaky

from ...provision import PackageSource
from ...provision._install import (
    uninstall_flocker,
    install_flocker,
    task_enable_flocker_agent,
    task_enable_docker_plugin,
    task_enable_flocker_control,
    ManagedNode
)
from ...provision._effect import sequence
from ...provision._ssh import run_remotely
from ...provision._ssh._conch import make_dispatcher

from ..testtools import (
    require_cluster, require_moving_backend, create_dataset, DatasetBackend
)



def upgrade_flocker(
    reactor, nodes, control_node, package_source, distribution
):
    """
    Put the version of Flocker indicated by ``package_source`` onto all of
    the given nodes.

    This takes a primitive approach of uninstalling the software and then
    installing the new version instead of trying to take advantage of any
    OS-level package upgrade support.  Because it's easier.  The package
    removal step is allowed to fail in case the package is not installed
    yet (other failures are not differentiated).  The only action taken on
    failure is that the failure is logged.

    :param pvector nodes: The ``ManagedNode``\ s on which to upgrade the
        software.
    :param PackageSource package_source: The version of the software to
        which to upgrade.

    :return: A ``Deferred`` that fires when the software has been upgraded.
    """
    managed_nodes = list(
        ManagedNode(address=node, distribution=distribution)
        for node in nodes
    )
    dispatcher = make_dispatcher(reactor)

    uninstalling = perform(dispatcher, uninstall_flocker(managed_nodes))

    uninstalling.addErrback(write_failure, logger=None)

    def install(ignored):
        return perform(
            dispatcher,
            install_flocker(managed_nodes, package_source),
        )
    uninstalling.addCallback(install)

    def restart_services(ignored):
        return perform(
            dispatcher,
            parallel([
                run_remotely(
                    username='root',
                    address=node.address,
                    commands=sequence([
                        task_enable_docker_plugin(node.distribution),
                        task_enable_flocker_agent(
                            distribution=node.distribution,
                            action='restart',
                        )
                    ])
                )
                for node in managed_nodes
            ] + [
                run_remotely(
                    username='root',
                    address=control_node,
                    commands=sequence([
                        task_enable_flocker_control(
                            distribution,
                            'restart'),
                    ])
                )
            ])
        )

    uninstalling.addCallback(restart_services)

    return uninstalling


class DatasetAPITests(AsyncTestCase):
    """
    Tests for the dataset API.
    """

    @flaky(u'FLOC-3207')
    @require_cluster(1)
    def test_dataset_creation(self, cluster):
        """
        A dataset can be created on a specific node.
        """
        return create_dataset(self, cluster)

    def _get_package_source(self, default_version=None):
        env_vars = ['FLOCKER_ACCEPTANCE_PACKAGE_BRANCH',
                    'FLOCKER_ACCEPTANCE_PACKAGE_VERSION',
                    'FLOCKER_ACCEPTANCE_PACKAGE_BUILD_SERVER']
        missing_vars = list(x for x in env_vars if x not in os.environ)
        if missing_vars:
            raise SkipTest(
                'Missing environment variables for upgrade test: %s.' %
                ', '.join(missing_vars))
        version = (
            os.environ['FLOCKER_ACCEPTANCE_PACKAGE_VERSION'] or default_version
        )
        return PackageSource(
            version=version,
            branch=os.environ['FLOCKER_ACCEPTANCE_PACKAGE_BRANCH'] or None,
            build_server=os.environ['FLOCKER_ACCEPTANCE_PACKAGE_BUILD_SERVER'])

    def _get_distribution(self):
        distribution = os.environ.get('FLOCKER_ACCEPTANCE_DISTRIBUTION')
        if distribution is None:
            raise SkipTest(
                'Missing environment variable FLOCKER_ACCEPTANCE_DISTRIBUTION '
                'which is required for upgrade test.')
        return distribution

    @run_test_with(async_runner(timeout=timedelta(minutes=6)))
    @require_cluster(1)
    def test_upgrade(self, cluster):
        node = cluster.nodes[0]
        SAMPLE_STR = '123456' * 100

        control_node_address = cluster.control_node.public_address
        all_cluster_nodes = set([x.public_address for x in cluster.nodes] +
                                [control_node_address])
        distribution = self._get_distribution()
        upgrade_from_version = get_installable_version(version)

        def get_flocker_version():
            d = cluster.client.version()
            d.addCallback(lambda v: str(v.get('flocker')) or None)
            return d

        def upgrade_flocker_to(package_source):
            d = get_flocker_version()

            def upgrade_if_needed(v):
                if v and v == package_source.version:
                    return v
                return upgrade_flocker(reactor, all_cluster_nodes,
                                       control_node_address, package_source,
                                       distribution)
            d.addCallback(upgrade_if_needed)

            d.addCallback(lambda _: get_flocker_version())

            def verify_version(v):
                print "VERSION:", v, "TARGET:", package_source.version
                if package_source.version:
                    self.assertEquals(
                        v, package_source.version,
                        "Failed to set version of flocker to %s, it is still "
                        "%s." % (package_source.version, v))
                return v
            d.addCallback(verify_version)

            return d

        # Get the initial flocker version and setup a cleanup call to restore
        # flocker to that version when the test is done.
        d = get_flocker_version()

        original_package_source = [None]

        def setup_restore_default(version):
            original_package_source[0] = (
                self._get_package_source(default_version=version))
            self.addCleanup(
                lambda: upgrade_flocker_to(original_package_source[0]))
            return version

        d.addCallback(setup_restore_default)

        # Downgrade flocker to the most recent released version.
        d.addCallback(
            lambda v: upgrade_flocker_to(
                PackageSource(version=upgrade_from_version)))

        return d

        # Create a dataset with the code from the most recent release.
        d.addCallback(lambda _: create_dataset(self, cluster, node=node))
        first_dataset = [None]

        # Write some data to a file in the dataset.
        def write_to_file(dataset):
            first_dataset[0] = dataset
            return node.run_as_root(
                ['bash', '-c', 'echo "%s" > %s' % (
                    SAMPLE_STR, os.path.join(dataset.path.path, 'test.txt'))])
        d.addCallback(write_to_file)

        # Upgrade flocker to the code under test.
        d.addCallback(lambda _: upgrade_flocker_to(original_package_source[0]))

        # Create a new dataset to convince ourselves that the new code is
        # running.
        d.addCallback(lambda _: create_dataset(self, cluster, node=node))

        # Wait for the first dataset to be mounted again.
        d.addCallback(lambda _: cluster.wait_for_dataset(first_dataset[0]))

        # Verify that the file still has its contents.
        def verify_file(dataset):
            return node.run_as_root(
                ['bash', '-c', 'cat %s' % (
                    os.path.join(dataset.path.path, 'test.txt'))])
        d.addCallback(verify_file)
        return d

    @require_cluster(1, required_backend=DatasetBackend.aws)
    def test_dataset_creation_with_gold_profile(self, cluster, backend):
        """
        A dataset created with the gold profile as specified in metadata on EBS
        has EBS volume type 'io1'.

        This is verified by constructing an EBS backend in this process, purely
        for the sake of using it as a wrapper on the cloud API.
        """
        waiting_for_create = create_dataset(
            self, cluster, maximum_size=4*1024*1024*1024,
            metadata={u"clusterhq:flocker:profile": u"gold"})

        def confirm_gold(dataset):
            volumes = backend.list_volumes()
            for volume in volumes:
                if volume.dataset_id == dataset.dataset_id:
                    break
            ebs_volume = backend._get_ebs_volume(volume.blockdevice_id)
            self.assertEqual('io1', ebs_volume.type)

        waiting_for_create.addCallback(confirm_gold)
        return waiting_for_create

    @flaky(u'FLOC-3341')
    @require_moving_backend
    @require_cluster(2)
    def test_dataset_move(self, cluster):
        """
        A dataset can be moved from one node to another.

        All attributes, including the maximum size, are preserved.
        """
        waiting_for_create = create_dataset(self, cluster)

        # Once created, request to move the dataset to node2
        def move_dataset(dataset):
            dataset_moving = cluster.client.move_dataset(
                UUID(cluster.nodes[1].uuid), dataset.dataset_id)

            # Wait for the dataset to be moved; we expect the state to
            # match that of the originally created dataset in all ways
            # other than the location.
            moved_dataset = dataset.set(
                primary=UUID(cluster.nodes[1].uuid))
            dataset_moving.addCallback(
                lambda dataset: cluster.wait_for_dataset(moved_dataset))
            return dataset_moving

        waiting_for_create.addCallback(move_dataset)
        return waiting_for_create

    @flaky(u'FLOC-3196')
    @require_cluster(1)
    def test_dataset_deletion(self, cluster):
        """
        A dataset can be deleted, resulting in its removal from the node.
        """
        created = create_dataset(self, cluster)

        def delete_dataset(dataset):
            deleted = cluster.client.delete_dataset(dataset.dataset_id)

            def not_exists():
                request = cluster.client.list_datasets_state()
                request.addCallback(
                    lambda actual_datasets: dataset.dataset_id not in
                    (d.dataset_id for d in actual_datasets))
                return request
            deleted.addCallback(lambda _: loop_until(reactor, not_exists))
            return deleted
        created.addCallback(delete_dataset)
        return created
