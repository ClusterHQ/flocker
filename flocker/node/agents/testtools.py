# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Test helpers for ``flocker.node.agents``.
"""

import os
from uuid import UUID, uuid4
from subprocess import STDOUT, PIPE, Popen, check_output
from functools import wraps
import psutil

from zope.interface.verify import verifyObject

from pyrsistent import InvariantException

from twisted.python.runtime import platform
from twisted.python.reflect import fullyQualifiedName
from twisted.python.filepath import FilePath
from twisted.trial.unittest import SynchronousTestCase, SkipTest

from eliot.testing import validate_logging, LoggedAction

from .blockdevice import (
    BlockDeviceDeployer, LoopbackBlockDeviceAPI, IBlockDeviceAPI,
    BlockDeviceVolume, UnknownVolume, AlreadyAttachedVolume,
    CreateBlockDeviceDataset, UnattachedVolume,
    DestroyBlockDeviceDataset, UnmountBlockDevice, DetachVolume,
    DestroyVolume,
    _losetup_list_parse, _losetup_list, _blockdevicevolume_from_dataset_id,
    DESTROY_BLOCK_DEVICE_DATASET, UNMOUNT_BLOCK_DEVICE, DETACH_VOLUME,
    DESTROY_VOLUME,
)

from .. import InParallel, IStateChange
from ..testtools import ideployer_tests_factory, to_node
from ...testtools import run_process
from ...control import (
    Dataset, Manifestation, Node, NodeState, Deployment, DeploymentState,
    NonManifestDatasets,
)


GIBIBYTE = 2 ** 30
REALISTIC_BLOCKDEVICE_SIZE = 4 * GIBIBYTE
LOOPBACK_BLOCKDEVICE_SIZE = 1024 * 1024 * 64


class IBlockDeviceAPITestsMixin(object):
    """
    Tests to perform on ``IBlockDeviceAPI`` providers.
    """
    def test_interface(self):
        """
        ``api`` instances provide ``IBlockDeviceAPI``.
        """
        self.assertTrue(
            verifyObject(IBlockDeviceAPI, self.api)
        )

    def test_list_volume_empty(self):
        """
        ``list_volumes`` returns an empty ``list`` if no block devices have
        been created.
        """
        self.assertEqual([], self.api.list_volumes())

    def test_created_is_listed(self):
        """
        ``create_volume`` returns a ``BlockVolume`` that is returned by
        ``list_volumes``.
        """
        dataset_id = uuid4()
        new_volume = self.api.create_volume(
            dataset_id=dataset_id,
            size=REALISTIC_BLOCKDEVICE_SIZE)
        self.assertIn(new_volume, self.api.list_volumes())

    def test_listed_volume_attributes(self):
        """
        ``list_volumes`` returns ``BlockVolume`` s that have a dataset_id.
        """
        expected_dataset_id = uuid4()
        self.api.create_volume(
            dataset_id=expected_dataset_id,
            size=REALISTIC_BLOCKDEVICE_SIZE
        )
        [listed_volume] = self.api.list_volumes()
        self.assertEqual(expected_dataset_id, listed_volume.dataset_id)

    def test_created_volume_attributes(self):
        """
        ``create_volume`` returns a ``BlockVolume`` that has a dataset_id
        """
        expected_dataset_id = uuid4()
        new_volume = self.api.create_volume(
            dataset_id=expected_dataset_id,
            size=REALISTIC_BLOCKDEVICE_SIZE
        )
        self.assertEqual(expected_dataset_id, new_volume.dataset_id)

    def test_attach_unknown_volume(self):
        """
        An attempt to attach an unknown ``BlockDeviceVolume`` raises
        ``UnknownVolume``.
        """
        self.assertRaises(
            UnknownVolume,
            self.api.attach_volume,
            blockdevice_id=unicode(uuid4()),
            # XXX This IP address and others in following tests need to be
            # parameterized so that these tests can be run against real cloud
            # nodes.
            host=u'192.0.2.123'
        )

    def test_attach_attached_volume(self):
        """
        An attempt to attach an already attached ``BlockDeviceVolume`` raises
        ``AlreadyAttachedVolume``.
        """
        host = u'192.0.2.123'
        dataset_id = uuid4()

        new_volume = self.api.create_volume(
            dataset_id=dataset_id,
            size=REALISTIC_BLOCKDEVICE_SIZE
        )
        attached_volume = self.api.attach_volume(
            new_volume.blockdevice_id, host=host
        )

        self.assertRaises(
            AlreadyAttachedVolume,
            self.api.attach_volume,
            blockdevice_id=attached_volume.blockdevice_id,
            host=host
        )

    def test_attach_elsewhere_attached_volume(self):
        """
        An attempt to attach a ``BlockDeviceVolume`` already attached to
        another host raises ``AlreadyAttachedVolume``.
        """
        new_volume = self.api.create_volume(
            dataset_id=uuid4(),
            size=REALISTIC_BLOCKDEVICE_SIZE
        )
        attached_volume = self.api.attach_volume(
            new_volume.blockdevice_id, host=u'192.0.2.123'
        )

        self.assertRaises(
            AlreadyAttachedVolume,
            self.api.attach_volume,
            blockdevice_id=attached_volume.blockdevice_id,
            host=u'192.0.2.124'
        )

    def test_attach_unattached_volume(self):
        """
        An unattached ``BlockDeviceVolume`` can be attached.
        """
        expected_host = u'192.0.2.123'
        dataset_id = uuid4()
        new_volume = self.api.create_volume(
            dataset_id=dataset_id,
            size=REALISTIC_BLOCKDEVICE_SIZE)
        expected_volume = BlockDeviceVolume(
            blockdevice_id=new_volume.blockdevice_id,
            size=new_volume.size,
            host=expected_host,
            dataset_id=dataset_id
        )
        attached_volume = self.api.attach_volume(
            blockdevice_id=new_volume.blockdevice_id,
            host=expected_host
        )
        self.assertEqual(expected_volume, attached_volume)

    def test_attached_volume_listed(self):
        """
        An attached ``BlockDeviceVolume`` is listed.
        """
        dataset_id = uuid4()
        expected_host = u'192.0.2.123'
        new_volume = self.api.create_volume(
            dataset_id=dataset_id,
            size=REALISTIC_BLOCKDEVICE_SIZE)
        expected_volume = BlockDeviceVolume(
            blockdevice_id=new_volume.blockdevice_id,
            size=new_volume.size,
            host=expected_host,
            dataset_id=dataset_id,
        )
        self.api.attach_volume(
            blockdevice_id=new_volume.blockdevice_id,
            host=expected_host
        )
        self.assertEqual([expected_volume], self.api.list_volumes())

    def test_list_attached_and_unattached(self):
        """
        ``list_volumes`` returns both attached and unattached
        ``BlockDeviceVolume``s.
        """
        expected_host = u'192.0.2.123'

        new_volume1 = self.api.create_volume(
            dataset_id=uuid4(),
            size=REALISTIC_BLOCKDEVICE_SIZE
        )
        new_volume2 = self.api.create_volume(
            dataset_id=uuid4(),
            size=REALISTIC_BLOCKDEVICE_SIZE
        )
        attached_volume = self.api.attach_volume(
            blockdevice_id=new_volume2.blockdevice_id,
            host=expected_host
        )
        self.assertItemsEqual(
            [new_volume1, attached_volume],
            self.api.list_volumes()
        )

    def test_multiple_volumes_attached_to_host(self):
        """
        ``attach_volume`` can attach multiple block devices to a single host.
        """
        expected_host = u'192.0.2.123'
        volume1 = self.api.create_volume(
            dataset_id=uuid4(),
            size=REALISTIC_BLOCKDEVICE_SIZE
        )
        volume2 = self.api.create_volume(
            dataset_id=uuid4(),
            size=REALISTIC_BLOCKDEVICE_SIZE
        )
        attached_volume1 = self.api.attach_volume(
            volume1.blockdevice_id, host=expected_host
        )
        attached_volume2 = self.api.attach_volume(
            volume2.blockdevice_id, host=expected_host
        )

        self.assertItemsEqual(
            [attached_volume1, attached_volume2],
            self.api.list_volumes()
        )

    def test_get_device_path_unknown_volume(self):
        """
        ``get_device_path`` raises ``UnknownVolume`` if the supplied
        ``blockdevice_id`` has not been created.
        """
        unknown_blockdevice_id = unicode(uuid4())
        exception = self.assertRaises(
            UnknownVolume,
            self.api.get_device_path,
            unknown_blockdevice_id
        )
        self.assertEqual(unknown_blockdevice_id, exception.blockdevice_id)

    def test_get_device_path_unattached_volume(self):
        """
        ``get_device_path`` raises ``UnattachedVolume`` if the supplied
        ``blockdevice_id`` corresponds to an unattached volume.
        """
        new_volume = self.api.create_volume(
            dataset_id=uuid4(),
            size=REALISTIC_BLOCKDEVICE_SIZE
        )
        exception = self.assertRaises(
            UnattachedVolume,
            self.api.get_device_path,
            new_volume.blockdevice_id
        )
        self.assertEqual(new_volume.blockdevice_id, exception.blockdevice_id)

    def test_get_device_path_device(self):
        """
        ``get_device_path`` returns a ``FilePath`` to the device representing
        the attached volume.
        """
        new_volume = self.api.create_volume(
            dataset_id=uuid4(),
            size=REALISTIC_BLOCKDEVICE_SIZE
        )
        attached_volume = self.api.attach_volume(
            new_volume.blockdevice_id,
            u'192.0.2.123'
        )
        device_path = self.api.get_device_path(attached_volume.blockdevice_id)
        self.assertTrue(
            device_path.isBlockDevice(),
            u"Not a block device. Path: {!r}".format(device_path)
        )

    def test_get_device_path_device_repeatable_results(self):
        """
        ``get_device_path`` returns the same ``FilePath`` for the volume device
        when called multiple times.
        """
        new_volume = self.api.create_volume(
            dataset_id=uuid4(),
            size=REALISTIC_BLOCKDEVICE_SIZE
        )
        attached_volume = self.api.attach_volume(
            new_volume.blockdevice_id,
            u'192.0.2.123'
        )

        device_path1 = self.api.get_device_path(attached_volume.blockdevice_id)
        device_path2 = self.api.get_device_path(attached_volume.blockdevice_id)

        self.assertEqual(device_path1, device_path2)

    def test_destroy_unknown_volume(self):
        """
        ``destroy_volume`` raises ``UnknownVolume`` if the supplied
        ``blockdevice_id`` does not exist.
        """
        blockdevice_id = unicode(uuid4)
        exception = self.assertRaises(
            UnknownVolume,
            self.api.destroy_volume, blockdevice_id=blockdevice_id
        )
        self.assertEqual(exception.args, (blockdevice_id,))

    def test_destroy_volume(self):
        """
        An unattached volume can be destroyed using ``destroy_volume``.
        """
        unrelated = self.api.create_volume(
            dataset_id=uuid4(),
            size=REALISTIC_BLOCKDEVICE_SIZE,
        )
        volume = self.api.create_volume(
            dataset_id=uuid4(),
            size=REALISTIC_BLOCKDEVICE_SIZE,
        )
        self.api.destroy_volume(volume.blockdevice_id)
        self.assertEqual([unrelated], self.api.list_volumes())

    def _destroyed_volume(self):
        """
        :return: A ``BlockDeviceVolume`` representing a volume which has been
            destroyed.
        """
        volume = self.api.create_volume(
            dataset_id=uuid4(), size=REALISTIC_BLOCKDEVICE_SIZE
        )
        self.api.destroy_volume(volume.blockdevice_id)
        return volume

    def test_destroy_destroyed_volume(self):
        """
        ``destroy_volume`` raises ``UnknownVolume`` if the supplied
        ``blockdevice_id`` was associated with a volume but that volume has
        been destroyed.
        """
        volume = self._destroyed_volume()
        exception = self.assertRaises(
            UnknownVolume,
            self.api.destroy_volume, blockdevice_id=volume.blockdevice_id
        )
        self.assertEqual(exception.args, (volume.blockdevice_id,))

    def test_detach_unknown_volume(self):
        """
        ``detach_volume`` raises ``UnknownVolume`` if the supplied
        ``blockdevice_id`` does not exist.
        """
        blockdevice_id = unicode(uuid4)
        exception = self.assertRaises(
            UnknownVolume,
            self.api.detach_volume, blockdevice_id=blockdevice_id
        )
        self.assertEqual(exception.args, (blockdevice_id,))

    def test_detach_detached_volume(self):
        """
        ``detach_volume`` raises ``UnattachedVolume`` if the supplied
        ``blockdevice_id`` is not attached to a host.
        """
        volume = self.api.create_volume(
            dataset_id=uuid4(), size=REALISTIC_BLOCKDEVICE_SIZE
        )
        exception = self.assertRaises(
            UnattachedVolume,
            self.api.detach_volume, volume.blockdevice_id
        )
        self.assertEqual(exception.args, (volume.blockdevice_id,))

    def test_detach_volume(self):
        """
        A volume that is attached becomes detached after ``detach_volume`` is
        called with its ``blockdevice_id``.
        """
        def fail_mount(device):
            mountpoint = FilePath(self.mktemp())
            mountpoint.makedirs()
            process = Popen(
                [b"mount", device_path.path, mountpoint.path],
                stdout=PIPE,
                stderr=STDOUT
            )
            output = process.stdout.read()
            process.wait()
            return output

        node = u"192.0.2.1"

        # Create an unrelated, attached volume that should be undisturbed.
        unrelated = self.api.create_volume(
            dataset_id=uuid4(), size=REALISTIC_BLOCKDEVICE_SIZE
        )
        unrelated = self.api.attach_volume(unrelated.blockdevice_id, node)

        # Create the volume we'll detach.
        volume = self.api.create_volume(
            dataset_id=uuid4(), size=REALISTIC_BLOCKDEVICE_SIZE
        )
        volume = self.api.attach_volume(
            volume.blockdevice_id, node
        )

        device_path = self.api.get_device_path(volume.blockdevice_id)

        attached_error = fail_mount(device_path)

        self.api.detach_volume(volume.blockdevice_id)

        self.assertEqual(
            {unrelated, volume.set(host=None)},
            set(self.api.list_volumes())
        )

        detached_error = fail_mount(device_path)

        # Make an incredibly indirect assertion to try to demonstrate we've
        # successfully detached the device.  The volume never had a filesystem
        # initialized on it so we couldn't mount it before when it was
        # attached.  Now that it's detached we still shouldn't be able to mount
        # it - but the reason we can't mount it should have changed.
        #
        # This isn't particularly great, no.
        self.assertNotEqual(attached_error, detached_error)

    def test_reattach_detached_volume(self):
        """
        A volume that has been detached can be re-attached.
        """
        node = u"192.0.2.4"
        # Create the volume we'll detach.
        volume = self.api.create_volume(
            dataset_id=uuid4(), size=REALISTIC_BLOCKDEVICE_SIZE
        )
        attached_volume = self.api.attach_volume(
            volume.blockdevice_id, node
        )
        self.api.detach_volume(volume.blockdevice_id)
        reattached_volume = self.api.attach_volume(
            volume.blockdevice_id, node
        )
        self.assertEqual(
            (attached_volume, [attached_volume]),
            (reattached_volume, self.api.list_volumes())
        )

    def test_attach_destroyed_volume(self):
        """
        ``attach_volume`` raises ``UnknownVolume`` when called with the
        ``blockdevice_id`` of a volume which has been destroyed.
        """
        node = u"192.0.2.5"
        volume = self._destroyed_volume()
        exception = self.assertRaises(
            UnknownVolume,
            self.api.attach_volume, volume.blockdevice_id, node
        )
        self.assertEqual(exception.args, (volume.blockdevice_id,))


def make_iblockdeviceapi_tests(blockdevice_api_factory):
    """
    :returns: A ``TestCase`` with tests that will be performed on the
       supplied ``IBlockDeviceAPI`` provider.
    """
    class Tests(IBlockDeviceAPITestsMixin, SynchronousTestCase):
        def setUp(self):
            self.api = blockdevice_api_factory(test_case=self)

    return Tests


def require_environment_variables(required_keys):
    """
    Get the values for each of ``keys`` from ``os.environ``.

    :param list keys: The key names to search for in ``os.environ``.
    :return: a ``dict`` of ``keys`` and corresponding values.
    :raises: ``SkipTest`` if any of the keys are not found in ``os.environ``.
    """
    def decorator(original):
        missing_keys = []
        keyvalues = {}

        for key in required_keys:
            value = os.environ.get(key, None)
            if value is None:
                missing_keys.append(key)
            else:
                keyvalues[key] = value

        @wraps(original)
        def wrapper(*args, **kwargs):
            if missing_keys:
                raise SkipTest(
                    '{!r} requires environment variables. '
                    'Required: "{}". '
                    'Missing: "{}".'.format(
                        fullyQualifiedName(original),
                        '", "'.join(required_keys),
                        '", "'.join(missing_keys),
                    )
                )
            updated_kwargs = dict(kwargs.items() + keyvalues.items())
            return original(*args, **updated_kwargs)
        return wrapper
    return decorator


def require_cinder_credentials(original):
    """
    Raise ``SkipTest`` unless the cinder username and api key are present in
    the environment.
    """
    decorator = require_environment_variables(
        required_keys=['OPENSTACK_API_USER', 'OPENSTACK_API_KEY']
    )
    return decorator(original)
