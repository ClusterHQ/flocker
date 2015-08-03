# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for the Volumes Plugin API provided by the plugin.
"""

from uuid import uuid4, UUID

from twisted.web.http import OK, CONFLICT

from .._api import VolumePlugin, DEFAULT_SIZE
from ...apiclient import FakeFlockerClient, Dataset
from ...control._config import dataset_id_from_name

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
        # Really we should be sending a blank body, but that has some
        # issues since @structured then expects a POST to have a
        # application/json content type. Fixing up the content type issues
        # (a necessary chunk of work) is covered by FLOC-2811, which
        # should also fix this.
        return self.assertResult(b"POST", b"/Plugin.Activate", {}, OK,
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

    def test_create_creates(self):
        """
        ``/VolumeDriver.Create`` creates a new dataset in the configuration.
        """
        name = u"myvol"
        d = self.assertResult(b"POST", b"/VolumeDriver.Create",
                              {u"Name": name}, OK, {u"Err": None})
        d.addCallback(lambda _: self.flocker_client.list_datasets_configuration())
        d.addCallback(self.assertItemsEqual, [
            Dataset(dataset_id=UUID(dataset_id_from_name(name)),
                    primary=self.NODE_A,
                    maximum_size=DEFAULT_SIZE,
                    deleted=False,
                    metadata={u"name": name})])
        return d

    def test_create_duplicate_name(self):
        """
        If a dataset with the given name already exists,
        ``/VolumeDriver.Create`` does not create a new volume, instead
        returning an error response.
        """
        name = u"thename"
        # Create a dataset out-of-band with matching name but non-matching
        # dataset ID:
        d = self.flocker_client.create_dataset(
            self.NODE_A, DEFAULT_SIZE, metadata={u"name": name})
        d.addCallback(lambda _: self.assertResult(
            b"POST", b"/VolumeDriver.Create",
            {u"Name": name}, CONFLICT, {u"Err": u"Duplicate volume name."}))
        return d

    def test_create_duplicate_name_race_condition(self):
        """
        If a dataset with the given name is created while the
        ``/VolumeDriver.Create`` call is in flight, the call does not
        create a new volume, instead returning an error response.
        """
        name = u"thename"

        # Create a dataset out-of-band with matching dataset ID but
        # non-matching name in metadata, after datasets are listed.
        # The docker plugin won't ever be able to tell that a dataset with
        # matching name exists.
        def create_after_list():
            # Clean up the patched version:
            del self.flocker_client.list_datasets_configuration
            # But first time we're called, we create dataset and lie about
            # its existence:
            d = self.flocker_client.create_dataset(
                self.NODE_A, DEFAULT_SIZE,
                dataset_id=UUID(dataset_id_from_name(name)))
            d.addCallback(lambda _: [])
            return d
        self.flocker_client.list_datasets_configuration = create_after_list

        return self.assertResult(
            b"POST", b"/VolumeDriver.Create",
            {u"Name": name}, CONFLICT, {u"Err": u"Duplicate volume name."})


def _build_app(test):
    test.initialize()
    return VolumePlugin(test.flocker_client, test.NODE_A).app
RealTestsAPI, MemoryTestsAPI = buildIntegrationTests(
    APITestsMixin, "API", _build_app)
