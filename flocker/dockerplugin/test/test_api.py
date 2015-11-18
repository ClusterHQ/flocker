# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for the Volumes Plugin API provided by the plugin.
"""

from uuid import uuid4, UUID

from twisted.web.http import OK, SERVICE_UNAVAILABLE
from twisted.internet import reactor
from twisted.internet.task import Clock, deferLater

from characteristic import attributes, Attribute

from .._api import VolumePlugin, DEFAULT_SIZE
from ...apiclient import FakeFlockerClient, Dataset
from ...control._config import dataset_id_from_name

from ...restapi.testtools import buildIntegrationTests, APIAssertionsMixin


@attributes([Attribute("call_count", default_value=0, instance_of=int)])
class CallCounter(object):
    pass

class APITestsMixin(APIAssertionsMixin):
    """
    Helpers for writing tests for the Docker Volume Plugin API.
    """
    NODE_A = uuid4()
    NODE_B = uuid4()

    def initialize(self):
        """
        Create initial objects for the ``VolumePlugin``.
        """
        self.reactor = Clock()
        self.flocker_client = FakeFlockerClient()

    def test_pluginactivate(self):
        """
        ``/Plugins.Activate`` indicates the plugin is a volume driver.
        """
        # Docker 1.8, at least, sends "null" as the body. Our test
        # infrastructure has the opposite bug so just going to send some
        # other garbage as the body (12345) to demonstrate that it's
        # ignored as per the spec which declares no body.
        return self.assertResult(b"POST", b"/Plugin.Activate", 12345, OK,
                                 {u"Implements": [u"VolumeDriver"]})

    def test_remove(self):
        """
        ``/VolumeDriver.Remove`` returns a successful result.
        """
        return self.assertResult(b"POST", b"/VolumeDriver.Remove",
                                 {u"Name": u"vol"}, OK, {u"Err": None})

    def test_unmount(self):
        """
        ``/VolumeDriver.Unmount`` returns a successful result.
        """
        return self.assertResult(b"POST", b"/VolumeDriver.Unmount",
                                 {u"Name": u"vol"}, OK, {u"Err": None})

    def test_create_with_opts(self):
        """
        Calling the ``/VolumerDriver.Create`` API with an ``Opts`` value
        in the request body JSON ignores this parameter and creates
        a volume with the given name.
        """
        name = u"testvolume"
        d = self.assertResult(b"POST", b"/VolumeDriver.Create",
                              {u"Name": name, 'Opts': {'ignored': 'ignored'}},
                              OK, {u"Err": None})
        d.addCallback(
            lambda _: self.flocker_client.list_datasets_configuration())
        d.addCallback(self.assertItemsEqual, [
            Dataset(dataset_id=UUID(dataset_id_from_name(name)),
                    primary=self.NODE_A,
                    maximum_size=DEFAULT_SIZE,
                    metadata={u"name": name})])
        return d

    def create(self, name):
        """
        Call the ``/VolumeDriver.Create`` API to create a volume with the
        given name.

        :param unicode name: The name of the volume to create.

        :return: ``Deferred`` that fires when the volume that was created.
        """
        return self.assertResult(b"POST", b"/VolumeDriver.Create",
                                 {u"Name": name}, OK, {u"Err": None})

    def test_create_creates(self):
        """
        ``/VolumeDriver.Create`` creates a new dataset in the configuration.
        """
        name = u"myvol"
        d = self.create(name)
        d.addCallback(
            lambda _: self.flocker_client.list_datasets_configuration())
        d.addCallback(self.assertItemsEqual, [
            Dataset(dataset_id=UUID(dataset_id_from_name(name)),
                    primary=self.NODE_A,
                    maximum_size=DEFAULT_SIZE,
                    metadata={u"name": name})])
        return d

    def test_create_duplicate_name(self):
        """
        If a dataset with the given name already exists,
        ``/VolumeDriver.Create`` succeeds without create a new volume.
        """
        name = u"thename"
        # Create a dataset out-of-band with matching name but non-matching
        # dataset ID:
        d = self.flocker_client.create_dataset(
            self.NODE_A, DEFAULT_SIZE, metadata={u"name": name})
        d.addCallback(lambda _: self.create(name))
        d.addCallback(
            lambda _: self.flocker_client.list_datasets_configuration())
        d.addCallback(lambda results: self.assertEqual(len(results), 1))
        return d

    def test_create_duplicate_name_race_condition(self):
        """
        If a dataset with the given name is created while the
        ``/VolumeDriver.Create`` call is in flight, the call does not
        result in an error.
        """
        name = u"thename"

        # Create a dataset out-of-band with matching dataset ID and name
        # which the docker plugin won't be able to see.
        def create_after_list():
            # Clean up the patched version:
            del self.flocker_client.list_datasets_configuration
            # But first time we're called, we create dataset and lie about
            # its existence:
            d = self.flocker_client.create_dataset(
                self.NODE_A, DEFAULT_SIZE,
                metadata={u"name": name},
                dataset_id=UUID(dataset_id_from_name(name)))
            d.addCallback(lambda _: [])
            return d
        self.flocker_client.list_datasets_configuration = create_after_list

        return self.create(name)

    def _patch_list_datasets_state_for_mount_test(self):
        """
        Patch self.flocker_client.list_datasets_state to advance
        ``self.reactor`` by `` _POLL_INTERVAL`` every time
        ``list_datasets_state`` is called. This is added at the end of the run
        queue so that ``volumedriver_mount`` has called ``deferLater`` before
        we advance the Clock.

        :returns: A ``CallCounter`` that is incremented every time
            list_datasets_state is incremented.
        """
        call_counter = CallCounter()

        def end_of_run_queue():
            return deferLater(reactor, 0.0, lambda: None)

        real_list_datasets_state = self.flocker_client.list_datasets_state

        def list_state_hack():
            end_of_run_queue().addCallback(
                lambda _: self.reactor.advance(VolumePlugin._POLL_INTERVAL))
            call_counter.call_count += 1
            return real_list_datasets_state()

        def restore_list_datasets_state():
            self.flocker_client.list_datasets_state = real_list_datasets_state
        self.addCleanup(restore_list_datasets_state)
        self.flocker_client.list_datasets_state = list_state_hack

        return call_counter

    def test_mount(self):
        """
        ``/VolumeDriver.Mount`` sets the primary of the dataset with matching
        name to the current node and then waits for the dataset to
        actually arrive.
        """
        name = u"myvol"
        dataset_id = UUID(dataset_id_from_name(name))
        # Create dataset on a different node:
        d = self.flocker_client.create_dataset(
            self.NODE_B, DEFAULT_SIZE, metadata={u"name": name},
            dataset_id=dataset_id)

        # Pretend that it takes 5 seconds for the dataset to get established on
        # Node A.
        self.reactor.callLater(5.0, self.flocker_client.synchronize_state)
        list_datasets_state = self._patch_list_datasets_state_for_mount_test()

        d.addCallback(lambda _:
                      self.assertResult(
                          b"POST", b"/VolumeDriver.Mount",
                          {u"Name": name}, OK,
                          {u"Err": None,
                           u"Mountpoint": u"/flocker/{}".format(dataset_id)}))
        d.addCallback(lambda _: self.flocker_client.list_datasets_state())

        def final_assertions(datasets):
            self.assertEqual([self.NODE_A],
                             [d.primary for d in datasets
                              if d.dataset_id == dataset_id])
            # There should be less than 20 calls to list_datasets_state over
            # the course of 5 seconds.
            self.assertLess(list_datasets_state.call_count, 20)
        d.addCallback(final_assertions)
        return d

    def test_mount_timeout(self):
        """
        ``/VolumeDriver.Mount`` sets the primary of the dataset with matching
        name to the current node and then waits for the dataset to
        actually arrive. If it does not arrive within 120 seconds, then it
        returns an error up to docker.
        """
        name = u"myvol"
        dataset_id = UUID(dataset_id_from_name(name))
        # Create dataset on a different node:
        d = self.flocker_client.create_dataset(
            self.NODE_B, DEFAULT_SIZE, metadata={u"name": name},
            dataset_id=dataset_id)

        # Do not call self.flocker_client.synchronize_state ever, in an attempt
        # to force the timeout of VolumeDriver.Mount.
        self._patch_list_datasets_state_for_mount_test()

        d.addCallback(lambda _:
                      self.assertResult(
                          b"POST", b"/VolumeDriver.Mount",
                          {u"Name": name}, SERVICE_UNAVAILABLE,
                          {u"Err": u"Timed out waiting for dataset to mount.",
                           u"Mountpoint": None}))
        return d

    def test_path(self):
        """
        ``/VolumeDriver.Path`` returns the mount path of the given volume if
        it is currently known.
        """
        name = u"myvol"
        dataset_id = UUID(dataset_id_from_name(name))

        d = self.create(name)
        # The dataset arrives as state:
        d.addCallback(lambda _: self.flocker_client.synchronize_state())

        d.addCallback(lambda _: self.assertResponseCode(
            b"POST", b"/VolumeDriver.Mount", {u"Name": name}, OK))

        d.addCallback(lambda _:
                      self.assertResult(
                          b"POST", b"/VolumeDriver.Path",
                          {u"Name": name}, OK,
                          {u"Err": None,
                           u"Mountpoint": u"/flocker/{}".format(dataset_id)}))
        return d

    def test_unknown_path(self):
        """
        ``/VolumeDriver.Path`` returns an error when asked for the mount path
        of a non-existent volume.
        """
        name = u"myvol"
        return self.assertResult(
            b"POST", b"/VolumeDriver.Path",
            {u"Name": name}, OK,
            {u"Err": u"Volume not available.", u"Mountpoint": u""})

    def test_non_local_path(self):
        """
        ``/VolumeDriver.Path`` returns an error when asked for the mount path
        of a volume that is not mounted locally.

        This can happen as a result of ``docker inspect`` on a container
        that has been created but is still waiting for its volume to
        arrive from another node. It seems like Docker may also call this
        after ``/VolumeDriver.Create``, so again while waiting for a
        volume to arrive.
        """
        name = u"myvol"
        dataset_id = UUID(dataset_id_from_name(name))

        # Create dataset on node B:
        d = self.flocker_client.create_dataset(
            self.NODE_B, DEFAULT_SIZE, metadata={u"name": name},
            dataset_id=dataset_id)
        d.addCallback(lambda _: self.flocker_client.synchronize_state())

        # Ask for path on node A:
        d.addCallback(lambda _:
                      self.assertResult(
                          b"POST", b"/VolumeDriver.Path",
                          {u"Name": name}, OK,
                          {u"Err": "Volume not available.",
                           u"Mountpoint": u""}))
        return d


def _build_app(test):
    test.initialize()
    return VolumePlugin(test.reactor, test.flocker_client, test.NODE_A).app
RealTestsAPI, MemoryTestsAPI = buildIntegrationTests(
    APITestsMixin, "API", _build_app)
