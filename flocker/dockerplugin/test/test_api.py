# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for the Volumes Plugin API provided by the plugin.
"""

from uuid import uuid4, UUID

from twisted.web.http import OK
from twisted.internet import reactor

from .._api import VolumePlugin, DEFAULT_SIZE
from ...apiclient import FakeFlockerClient, Dataset
from ...control._config import dataset_id_from_name

from ...node.testtools import require_docker_version

from ...restapi.testtools import buildIntegrationTests, APIAssertionsMixin


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

    @require_docker_version(
        '1.9.0',
        'This test uses the v2 plugin API, which requires Docker >=1.9.0'
    )
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

        # After two polling intervals the dataset arrives as state:
        reactor.callLater(VolumePlugin._POLL_INTERVAL,
                          self.flocker_client.synchronize_state)

        d.addCallback(lambda _:
                      self.assertResult(
                          b"POST", b"/VolumeDriver.Mount",
                          {u"Name": name}, OK,
                          {u"Err": None,
                           u"Mountpoint": u"/flocker/{}".format(dataset_id)}))
        d.addCallback(lambda _: self.flocker_client.list_datasets_state())
        d.addCallback(lambda ds: self.assertEqual(
            [self.NODE_A], [d.primary for d in ds
                            if d.dataset_id == dataset_id]))
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
    return VolumePlugin(reactor, test.flocker_client, test.NODE_A).app
RealTestsAPI, MemoryTestsAPI = buildIntegrationTests(
    APITestsMixin, "API", _build_app)
