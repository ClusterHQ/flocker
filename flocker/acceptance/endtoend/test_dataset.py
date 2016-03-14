# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for the datasets REST API.
"""
import os

from datetime import timedelta
from uuid import UUID, uuid4
from unittest import SkipTest, skipIf

from testtools import run_test_with
from testtools.matchers import MatchesListwise, AfterPreprocessing, Equals
from twisted.internet import reactor


from flocker import __version__ as HEAD_FLOCKER_VERSION
from flocker.common.version import get_installable_version
from ...common import loop_until
from ...testtools import AsyncTestCase, flaky, async_runner
from ...node.agents.blockdevice import ICloudAPI

from ...provision import PackageSource

from ...node import backends

from ..testtools import (
    require_cluster, require_moving_backend, create_dataset,
    skip_backend, get_backend_api, verify_socket,
    get_default_volume_size,
)


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
        """
        Get the package source for the flocker version under test from
        environment variables.

        The environment variables that will be read are as follows. Note that
        if any of them are not specified the test will be skipped.

        FLOCKER_ACCEPTANCE_PACKAGE_BRANCH:
            The branch to build from or an empty string to use the default.
        FLOCKER_ACCEPTANCE_PACKAGE_VERSION:
            The version of the package of flocker under test or the empty
            string to use the default.
        FLOCKER_ACCEPTANCE_PACKAGE_BUILD_SERVER:
            The build server from which to download the flocker package under
            test.

        :param unicode default_version: The version of flocker to use
            if the ``FLOCKER_ACCEPTANCE_PACKAGE_VERSION`` specifies to use the
            default.

        :return: A ``PackageSource`` that can be used to install the version of
            flocker under test.
        """
        env_vars = ['FLOCKER_ACCEPTANCE_PACKAGE_BRANCH',
                    'FLOCKER_ACCEPTANCE_PACKAGE_VERSION',
                    'FLOCKER_ACCEPTANCE_PACKAGE_BUILD_SERVER']
        defaultable = frozenset(['FLOCKER_ACCEPTANCE_PACKAGE_BRANCH',
                                 'FLOCKER_ACCEPTANCE_PACKAGE_VERSION'])
        missing_vars = list(var for var in env_vars if var not in os.environ)
        if missing_vars:
            message = ('Missing environment variables for upgrade test: %s.' %
                       ', '.join(missing_vars))
            missing_defaultable = list(var for var in missing_vars
                                       if var in defaultable)
            if missing_defaultable:
                message += (' Note that (%s) can be set to an empty string to '
                            'use a default value' %
                            ', '.join(missing_defaultable))
            raise SkipTest(message)
        version = (os.environ['FLOCKER_ACCEPTANCE_PACKAGE_VERSION'] or
                   default_version)
        return PackageSource(
            version=version,
            branch=os.environ['FLOCKER_ACCEPTANCE_PACKAGE_BRANCH'],
            build_server=os.environ['FLOCKER_ACCEPTANCE_PACKAGE_BUILD_SERVER'])

    @skip_backend(
        unsupported={backends.LOOPBACK},
        reason="Does not maintain compute_instance_id across restarting "
               "flocker (and didn't as of most recent release).")
    @skip_backend(
        unsupported={backends.GCE},
        # XXX: FLOC-4297: Enable this after the next marketing release.
        reason="GCE was not available during the most recent release.")
    @run_test_with(async_runner(timeout=timedelta(minutes=6)))
    @require_cluster(1)
    def test_upgrade(self, cluster):
        """
        Given a dataset created and used with the previously installable
        version of flocker, uninstalling the previous version of flocker and
        installing HEAD does not destroy the data on the dataset.
        """
        node = cluster.nodes[0]
        SAMPLE_STR = '123456' * 100

        upgrade_from_version = get_installable_version(HEAD_FLOCKER_VERSION)

        # Get the initial flocker version and setup a cleanup call to restore
        # flocker to that version when the test is done.
        d = cluster.client.version()
        original_package_source = [None]

        def setup_restore_original_flocker(version):
            version_bytes = version.get('flocker', u'').encode('ascii')
            original_package_source[0] = (
                self._get_package_source(
                    default_version=version_bytes or None)
            )
            self.addCleanup(
                lambda: cluster.install_flocker_version(
                    original_package_source[0]))
            return version

        d.addCallback(setup_restore_original_flocker)

        # Double check that the nodes are clean before we destroy the persisted
        # state.
        d.addCallback(lambda _: cluster.clean_nodes())

        # Downgrade flocker to the most recent released version.
        d.addCallback(
            lambda _: cluster.install_flocker_version(
                PackageSource(version=upgrade_from_version),
                destroy_persisted_state=True
            )
        )

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
        d.addCallback(lambda _: cluster.install_flocker_version(
            original_package_source[0]))

        # Create a new dataset to convince ourselves that the new code is
        # running.
        d.addCallback(lambda _: create_dataset(self, cluster, node=node))

        # Wait for the first dataset to be mounted again.
        d.addCallback(lambda _: cluster.wait_for_dataset(first_dataset[0]))

        # Verify that the file still has its contents.
        def cat_and_verify_file(dataset):
            output = []

            file_catting = node.run_as_root(
                ['bash', '-c', 'cat %s' % (
                    os.path.join(dataset.path.path, 'test.txt'))],
                handle_stdout=output.append)

            def verify_file(_):
                file_contents = ''.join(output)
                self.assertEqual(file_contents, SAMPLE_STR)

            file_catting.addCallback(verify_file)
            return file_catting
        d.addCallback(cat_and_verify_file)
        return d

    @require_cluster(1, required_backend=backends.AWS)
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
            matching = [
                v for v in volumes if v.dataset_id == dataset.dataset_id]
            volume_types = [
                backend._get_ebs_volume(v.blockdevice_id).volume_type
                for v in matching]
            self.assertEqual(volume_types, ['io1'])

        waiting_for_create.addCallback(confirm_gold)
        return waiting_for_create

    @flaky(u'FLOC-3341')
    @require_moving_backend
    # GCE sometimes takes 1 full minute to detach a disk.
    @run_test_with(async_runner(timeout=timedelta(minutes=4)))
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

    @skipIf(True,
            "Shutting down a node invalidates a public IP, which breaks all "
            "kinds of things. So skip for now.")
    @require_moving_backend
    @run_test_with(async_runner(timeout=timedelta(minutes=6)))
    @require_cluster(2)
    def test_dataset_move_from_dead_node(self, cluster):
        """
        A dataset can be moved from a dead node to a live node.

        All attributes, including the maximum size, are preserved.
        """
        api = get_backend_api(cluster.cluster_uuid)
        if not ICloudAPI.providedBy(api):
            raise SkipTest(
                "Backend doesn't support ICloudAPI; therefore it might support"
                " moving from dead node but as first pass we assume it "
                "doesn't.")

        # Find a node which is not running the control service.
        # If the control node is shut down we won't be able to move anything!
        node = list(node for node in cluster.nodes
                    if node.public_address !=
                    cluster.control_node.public_address)[0]
        other_node = list(other_node for other_node in cluster.nodes
                          if other_node != node)[0]
        waiting_for_create = create_dataset(self, cluster, node=node)

        def startup_node(node_id):
            api.start_node(node_id)
            # Wait for node to boot up:; we presume Flocker getting going after
            # SSH is available will be pretty quick:
            return loop_until(reactor, verify_socket(node.public_address, 22))

        # Once created, shut down origin node and then request to move the
        # dataset to node2:
        def shutdown(dataset):
            live_node_ids = set(api.list_live_nodes())
            d = node.shutdown()
            # Wait for shutdown to be far enough long that node is down:
            d.addCallback(
                lambda _:
                loop_until(reactor, lambda:
                           set(api.list_live_nodes()) != live_node_ids))
            # Schedule node start up:
            d.addCallback(
                lambda _: self.addCleanup(
                    startup_node,
                    (live_node_ids - set(api.list_live_nodes())).pop()))
            d.addCallback(lambda _: dataset)
            return d
        waiting_for_shutdown = waiting_for_create.addCallback(shutdown)

        def move_dataset(dataset):
            dataset_moving = cluster.client.move_dataset(
                UUID(other_node.uuid), dataset.dataset_id)

            # Wait for the dataset to be moved; we expect the state to
            # match that of the originally created dataset in all ways
            # other than the location.
            moved_dataset = dataset.set(
                primary=UUID(other_node.uuid))
            dataset_moving.addCallback(
                lambda dataset: cluster.wait_for_dataset(moved_dataset))
            return dataset_moving

        waiting_for_shutdown.addCallback(move_dataset)
        return waiting_for_shutdown

    @require_cluster(1)
    def test_unregistered_volume(self, cluster):
        """
        If there is already a backend volume for a dataset when it is created,
        that volume is used for that dataset.
        """
        api = get_backend_api(cluster.cluster_uuid)

        # Create a volume for a dataset
        dataset_id = uuid4()
        volume = api.create_volume(dataset_id, size=get_default_volume_size())

        # Then create the coresponding dataset.
        wait_for_dataset = create_dataset(self, cluster, dataset_id=dataset_id)

        def check_volumes(dataset):
            new_volumes = api.list_volumes()
            # That volume should be the only dataset in the cluster.
            # Clear `.attached_to` on the new volume, since we expect it to be
            # attached.
            self.assertThat(
                new_volumes,
                MatchesListwise([
                    AfterPreprocessing(
                        lambda new_volume: new_volume.set('attached_to', None),
                        Equals(volume)
                    ),
                ])
            )
        wait_for_dataset.addCallback(check_volumes)
        return wait_for_dataset

    @skip_backend(
        unsupported={backends.GCE},
        reason="The GCE backend does not let you create two volumes with the "
               "same dataset id. When this test is run with GCE the test "
               "fails to create the extra volume, and we do not test the "
               "functionality this test was designed to test.")
    @require_cluster(2)
    def test_extra_volume(self, cluster):
        """
        If an extra volume is created for a dataset, that volume isn't used.

        .. note:
           This test will be flaky if flocker doesn't correctly ignore extra
           volumes that claim to belong to a dataset, since the dataset picked
           will be random.
        """
        api = get_backend_api(cluster.cluster_uuid)

        # Create the dataset
        wait_for_dataset = create_dataset(self, cluster)

        created_volume = []

        # Create an extra volume claiming to belong to that dataset
        def create_extra(dataset):
            # Create a second volume for that dataset
            volume = api.create_volume(dataset.dataset_id,
                                       size=get_default_volume_size())
            created_volume.append(volume)
            return dataset

        wait_for_extra_volume = wait_for_dataset.addCallback(create_extra)

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
        wait_for_move = wait_for_extra_volume.addCallback(move_dataset)

        # Check that the extra volume isn't attached to a node.
        # This indicates that the originally created volume is attached.
        def check_attached(dataset):
            blockdevice_id = created_volume[0].blockdevice_id
            [volume] = [volume for volume in api.list_volumes()
                        if volume.blockdevice_id == blockdevice_id]

            self.assertEqual(volume.attached_to, None)

        return wait_for_move.addCallback(check_attached)

        return wait_for_dataset
