# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for the Volumes Plugin API provided by the plugin.
"""

from uuid import uuid4

from bitmath import TiB, GiB, MiB, KiB, Byte

from twisted.web.http import OK, NOT_ALLOWED, NOT_FOUND
from twisted.internet.task import Clock, LoopingCall
from twisted.internet.defer import gatherResults

from hypothesis import given
from hypothesis.strategies import (
    sampled_from, builds, integers
)

from pyrsistent import pmap

from eliot.testing import capture_logging

from .._api import VolumePlugin, DEFAULT_SIZE, parse_num, NAME_FIELD
from ...apiclient import FakeFlockerClient, Dataset, DatasetsConfiguration
from ...testtools import CustomException, random_name

from ...restapi import make_bad_request
from ...restapi.testtools import (
    build_UNIX_integration_tests, APIAssertionsMixin,
)


# A Hypothesis strategy for generating size expression of volume
# don't bother with kib, or mib it's too small, tib too big.
volume_expression = builds(
    lambda expression: b"".join(expression),
    expression=sampled_from([u"GB", "gib", "G", "Gb", "gb", "Gib", "g"]),
)


class SimpleCountingProxy(object):
    """
    Transparent proxy that counts the number of calls to methods of the
    wrapped object.

    :ivar _wrapped: Wrapped object.
    :ivar call_count: Mapping of method name to number of calls.
    """
    def __init__(self, wrapped):
        self._wrapped = wrapped
        self.call_count = pmap()

    def num_calls(self, name):
        """
        Return the number of times the given method was called with given
        arguments.

        :param name: Method name.

        :return: Number of calls.
        """
        return self.call_count.get(name, 0)

    def __getattr__(self, name):
        method = getattr(self._wrapped, name)

        def counting_proxy(*args, **kwargs):
            current_count = self.call_count.get(name, 0)
            self.call_count = self.call_count.set(name, current_count + 1)
            return method(*args, **kwargs)
        return counting_proxy


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
        self.volume_plugin_reactor = Clock()
        self.flocker_client = SimpleCountingProxy(FakeFlockerClient())
        # The conditional_create operation used by the plugin relies on
        # the passage of time... so make sure time passes! We still use a
        # fake clock since some tests want to skip ahead.
        self.looping = LoopingCall(
            lambda: self.volume_plugin_reactor.advance(0.001))
        self.looping.start(0.001)
        self.addCleanup(self.looping.stop)

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
                                 {u"Name": u"vol"}, OK, {u"Err": u""})

    def test_unmount(self):
        """
        ``/VolumeDriver.Unmount`` returns a successful result.
        """
        return self.assertResult(b"POST", b"/VolumeDriver.Unmount",
                                 {u"Name": u"vol"}, OK, {u"Err": u""})

    def test_create_with_profile(self):
        """
        Calling the ``/VolumerDriver.Create`` API with an ``Opts`` value
        of "profile=[gold,silver,bronze] in the request body JSON create a
        volume with a given name with [gold,silver,bronze] profile.
        """
        profile = sampled_from(["gold", "silver", "bronze"]).example()
        name = random_name(self)
        d = self.assertResult(b"POST", b"/VolumeDriver.Create",
                              {u"Name": name, 'Opts': {u"profile": profile}},
                              OK, {u"Err": u""})
        d.addCallback(
            lambda _: self.flocker_client.list_datasets_configuration())
        d.addCallback(list)
        d.addCallback(lambda result:
                      self.assertItemsEqual(
                          result, [
                              Dataset(dataset_id=result[0].dataset_id,
                                      primary=self.NODE_A,
                                      maximum_size=int(DEFAULT_SIZE.to_Byte()),
                                      metadata={NAME_FIELD: name,
                                                u"clusterhq:flocker:profile":
                                                unicode(profile)})]))
        return d

    def test_create_with_size(self):
        """
        Calling the ``/VolumerDriver.Create`` API with an ``Opts`` value
        of "size=<somesize> in the request body JSON create a volume
        with a given name and random size between 1-100G
        """
        name = random_name(self)
        size = integers(min_value=1, max_value=75).example()
        expression = volume_expression.example()
        size_opt = "".join(str(size))+expression
        d = self.assertResult(b"POST", b"/VolumeDriver.Create",
                              {u"Name": name, 'Opts': {u"size": size_opt}},
                              OK, {u"Err": u""})

        real_size = int(parse_num(size_opt).to_Byte())
        d.addCallback(
            lambda _: self.flocker_client.list_datasets_configuration())
        d.addCallback(list)
        d.addCallback(lambda result:
                      self.assertItemsEqual(
                          result, [
                              Dataset(dataset_id=result[0].dataset_id,
                                      primary=self.NODE_A,
                                      maximum_size=real_size,
                                      metadata={NAME_FIELD: name,
                                                u"maximum_size":
                                                unicode(real_size)})]))
        return d

    @given(expr=volume_expression,
           size=integers(min_value=75, max_value=100))
    def test_parsenum_size(self, expr, size):
        """
        Send different forms of size expressions
        to ``parse_num``, we expect G(Gigabyte) size results.

        :param expr str: A string representing the size expression
        :param size int: A string representing the volume size
        """
        expected_size = int(GiB(size).to_Byte())
        return self.assertEqual(expected_size,
                                int(parse_num(str(size)+expr).to_Byte()))

    @given(expr=sampled_from(["KB", "MB", "GB", "TB", ""]),
           size=integers(min_value=1, max_value=100))
    def test_parsenum_all_sizes(self, expr, size):
        """
        Send standard size expressions to ``parse_num`` in
        many sizes, we expect to get correct size results.

        :param expr str: A string representing the size expression
        :param size int: A string representing the volume size
        """
        if expr is "KB":
            expected_size = int(KiB(size).to_Byte())
        elif expr is "MB":
            expected_size = int(MiB(size).to_Byte())
        elif expr is "GB":
            expected_size = int(GiB(size).to_Byte())
        elif expr is "TB":
            expected_size = int(TiB(size).to_Byte())
        else:
            expected_size = int(Byte(size).to_Byte())
        return self.assertEqual(expected_size,
                                int(parse_num(str(size)+expr).to_Byte()))

    @given(size=sampled_from([u"foo10Gb", u"10bar10", "10foogib",
                              "10Gfoo", "GIB", "bar10foo"]))
    def test_parsenum_bad_size(self, size):
        """
        Send unacceptable size expressions, upon error
        users should expect to receive Flocker's ``DEFAULT_SIZE``

        :param size str: A string representing the bad volume size
        """
        return self.assertEqual(int(DEFAULT_SIZE.to_Byte()),
                                int(parse_num(size).to_Byte()))

    def create(self, name):
        """
        Call the ``/VolumeDriver.Create`` API to create a volume with the
        given name.

        :param unicode name: The name of the volume to create.

        :return: ``Deferred`` that fires when the volume that was created.
        """
        return self.assertResult(b"POST", b"/VolumeDriver.Create",
                                 {u"Name": name}, OK, {u"Err": u""})

    def test_create_creates(self):
        """
        ``/VolumeDriver.Create`` creates a new dataset in the configuration.
        """
        name = u"myvol"
        d = self.create(name)
        d.addCallback(
            lambda _: self.flocker_client.list_datasets_configuration())
        d.addCallback(list)
        d.addCallback(lambda result:
                      self.assertItemsEqual(
                          result, [
                              Dataset(dataset_id=result[0].dataset_id,
                                      primary=self.NODE_A,
                                      maximum_size=int(DEFAULT_SIZE.to_Byte()),
                                      metadata={NAME_FIELD: name})]))
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
            self.NODE_A, int(DEFAULT_SIZE.to_Byte()),
            metadata={NAME_FIELD: name})
        d.addCallback(lambda _: self.create(name))
        d.addCallback(
            lambda _: self.flocker_client.list_datasets_configuration())
        d.addCallback(lambda results: self.assertEqual(len(list(results)), 1))
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
                self.NODE_A, int(DEFAULT_SIZE.to_Byte()),
                metadata={NAME_FIELD: name})
            d.addCallback(lambda _: DatasetsConfiguration(
                tag=u"1234", datasets={}))
            return d
        self.flocker_client.list_datasets_configuration = create_after_list

        return self.create(name)

    def _flush_volume_plugin_reactor_on_endpoint_render(self):
        """
        This method patches ``self.app`` so that after any endpoint is
        rendered, the reactor used by the volume plugin is advanced repeatedly
        until there are no more ``delayedCalls`` pending on the reactor.
        """
        real_execute_endpoint = self.app.execute_endpoint

        def patched_execute_endpoint(*args, **kwargs):
            val = real_execute_endpoint(*args, **kwargs)
            while self.volume_plugin_reactor.getDelayedCalls():
                pending_calls = self.volume_plugin_reactor.getDelayedCalls()
                next_expiration = min(t.getTime() for t in pending_calls)
                now = self.volume_plugin_reactor.seconds()
                self.volume_plugin_reactor.advance(
                    max(0.0, next_expiration - now))
            return val
        self.patch(self.app, 'execute_endpoint', patched_execute_endpoint)

    def test_mount(self):
        """
        ``/VolumeDriver.Mount`` sets the primary of the dataset with matching
        name to the current node and then waits for the dataset to
        actually arrive.
        """
        name = u"myvol"
        dataset_id = uuid4()

        # Create dataset on a different node:
        d = self.flocker_client.create_dataset(
            self.NODE_B, int(DEFAULT_SIZE.to_Byte()),
            metadata={NAME_FIELD: name},
            dataset_id=dataset_id)

        self._flush_volume_plugin_reactor_on_endpoint_render()

        # Pretend that it takes 5 seconds for the dataset to get established on
        # Node A.
        self.volume_plugin_reactor.callLater(
            5.0, self.flocker_client.synchronize_state)

        d.addCallback(lambda _:
                      self.assertResult(
                          b"POST", b"/VolumeDriver.Mount",
                          {u"Name": name}, OK,
                          {u"Err": u"",
                           u"Mountpoint": u"/flocker/{}".format(dataset_id)}))
        d.addCallback(lambda _: self.flocker_client.list_datasets_state())

        def final_assertions(datasets):
            self.assertEqual([self.NODE_A],
                             [d.primary for d in datasets
                              if d.dataset_id == dataset_id])
            # There should be less than 20 calls to list_datasets_state over
            # the course of 5 seconds.
            self.assertLess(
                self.flocker_client.num_calls('list_datasets_state'), 20)
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
        dataset_id = uuid4()
        # Create dataset on a different node:
        d = self.flocker_client.create_dataset(
            self.NODE_B, int(DEFAULT_SIZE.to_Byte()),
            metadata={NAME_FIELD: name},
            dataset_id=dataset_id)

        self._flush_volume_plugin_reactor_on_endpoint_render()

        # Pretend that it takes 500 seconds for the dataset to get established
        # on Node A. This should be longer than the timeout.
        self.volume_plugin_reactor.callLater(
            500.0, self.flocker_client.synchronize_state)

        d.addCallback(lambda _:
                      self.assertResult(
                          b"POST", b"/VolumeDriver.Mount",
                          {u"Name": name}, OK,
                          {u"Err": u"Timed out waiting for dataset to mount.",
                           u"Mountpoint": u""}))
        return d

    def test_mount_already_exists(self):
        """
        ``/VolumeDriver.Mount`` sets the primary of the dataset with matching
        name to the current node and then waits for the dataset to
        actually arrive when used by the volumes that already exist and
        don't have a special dataset ID.
        """
        name = u"myvol"

        d = self.flocker_client.create_dataset(
            self.NODE_A, int(DEFAULT_SIZE.to_Byte()),
            metadata={NAME_FIELD: name})

        def created(dataset):
            self.flocker_client.synchronize_state()
            result = self.assertResult(
                b"POST", b"/VolumeDriver.Mount",
                {u"Name": name}, OK,
                {u"Err": u"",
                 u"Mountpoint": u"/flocker/{}".format(
                     dataset.dataset_id)})
            result.addCallback(lambda _:
                               self.flocker_client.list_datasets_state())
            result.addCallback(lambda ds: self.assertEqual(
                [self.NODE_A], [d.primary for d in ds
                                if d.dataset_id == dataset.dataset_id]))
            return result
        d.addCallback(created)
        return d

    def test_unknown_mount(self):
        """
        ``/VolumeDriver.Mount`` returns an error when asked to mount a
        non-existent volume.
        """
        name = u"myvol"
        return self.assertResult(
            b"POST", b"/VolumeDriver.Mount",
            {u"Name": name}, OK,
            {u"Err": u"Could not find volume with given name."})

    def test_path(self):
        """
        ``/VolumeDriver.Path`` returns the mount path of the given volume if
        it is currently known.
        """
        name = u"myvol"

        d = self.create(name)
        # The dataset arrives as state:
        d.addCallback(lambda _: self.flocker_client.synchronize_state())

        d.addCallback(lambda _: self.assertResponseCode(
            b"POST", b"/VolumeDriver.Mount", {u"Name": name}, OK))
        d.addCallback(lambda _:
                      self.flocker_client.list_datasets_configuration())
        d.addCallback(lambda datasets_config:
                      self.assertResult(
                          b"POST", b"/VolumeDriver.Path",
                          {u"Name": name}, OK,
                          {u"Err": u"",
                           u"Mountpoint": u"/flocker/{}".format(
                               datasets_config.datasets.keys()[0])}))
        return d

    def test_path_existing(self):
        """
        ``/VolumeDriver.Path`` returns the mount path of the given volume if
        it is currently known, including for a dataset that was created
        not by the plugin.
        """
        name = u"myvol"

        d = self.flocker_client.create_dataset(
            self.NODE_A, int(DEFAULT_SIZE.to_Byte()),
            metadata={NAME_FIELD: name})

        def created(dataset):
            self.flocker_client.synchronize_state()
            return self.assertResult(
                b"POST", b"/VolumeDriver.Path",
                {u"Name": name}, OK,
                {u"Err": u"",
                 u"Mountpoint": u"/flocker/{}".format(dataset.dataset_id)})
        d.addCallback(created)
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
            {u"Err": u"Could not find volume with given name."})

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
        dataset_id = uuid4()

        # Create dataset on node B:
        d = self.flocker_client.create_dataset(
            self.NODE_B, int(DEFAULT_SIZE.to_Byte()),
            metadata={NAME_FIELD: name},
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

    @capture_logging(lambda self, logger:
                     self.assertEqual(
                         len(logger.flushTracebacks(CustomException)), 1))
    def test_unexpected_error_reporting(self, logger):
        """
        If an unexpected error occurs Docker gets back a useful error message.
        """
        def error():
            raise CustomException("I've made a terrible mistake")
        self.patch(self.flocker_client, "list_datasets_configuration",
                   error)
        return self.assertResult(
            b"POST", b"/VolumeDriver.Path",
            {u"Name": u"whatever"}, OK,
            {u"Err": "CustomException: I've made a terrible mistake"})

    @capture_logging(None)
    def test_bad_request(self, logger):
        """
        If a ``BadRequest`` exception is raised it is converted to appropriate
        JSON.
        """
        def error():
            raise make_bad_request(code=423, Err=u"no good")
        self.patch(self.flocker_client, "list_datasets_configuration",
                   error)
        return self.assertResult(
            b"POST", b"/VolumeDriver.Path",
            {u"Name": u"whatever"}, 423,
            {u"Err": "no good"})

    def test_unsupported_method(self):
        """
        If an unsupported method is requested the 405 Not Allowed response
        code is returned.
        """
        return self.assertResponseCode(
            b"BAD_METHOD", b"/VolumeDriver.Path", None, NOT_ALLOWED)

    def test_unknown_uri(self):
        """
        If an unknown URI path is requested the 404 Not Found response code is
        returned.
        """
        return self.assertResponseCode(
            b"BAD_METHOD", b"/xxxnotthere", None, NOT_FOUND)

    def test_empty_host(self):
        """
        If an empty host header is sent to the Docker plugin it does not blow
        up, instead operating normally. E.g. for ``Plugin.Activate`` call
        returns the ``Implements`` response.
        """
        return self.assertResult(b"POST", b"/Plugin.Activate", 12345, OK,
                                 {u"Implements": [u"VolumeDriver"]},
                                 additional_headers={b"Host": [""]})

    def test_get(self):
        """
        ``/VolumeDriver.Get`` returns the mount path of the given volume if
        it is currently known.
        """
        name = u"myvol"

        d = self.create(name)
        # The dataset arrives as state:
        d.addCallback(lambda _: self.flocker_client.synchronize_state())

        d.addCallback(lambda _: self.assertResponseCode(
            b"POST", b"/VolumeDriver.Mount", {u"Name": name}, OK))
        d.addCallback(lambda _:
                      self.flocker_client.list_datasets_configuration())
        d.addCallback(lambda datasets_config:
                      self.assertResult(
                          b"POST", b"/VolumeDriver.Get",
                          {u"Name": name}, OK,
                          {u"Err": u"",
                           u"Volume": {
                               u"Name": name,
                               u"Mountpoint": u"/flocker/{}".format(
                                   datasets_config.datasets.keys()[0])}}))
        return d

    def test_get_existing(self):
        """
        ``/VolumeDriver.Get`` returns the mount path of the given volume if
        it is currently known, including for a dataset that was created
        not by the plugin.
        """
        name = u"myvol"

        d = self.flocker_client.create_dataset(
            self.NODE_A, int(DEFAULT_SIZE.to_Byte()),
            metadata={NAME_FIELD: name})

        def created(dataset):
            self.flocker_client.synchronize_state()
            return self.assertResult(
                b"POST", b"/VolumeDriver.Get",
                {u"Name": name}, OK,
                {u"Err": u"",
                 u"Volume": {
                     u"Name": name,
                     u"Mountpoint":
                     u"/flocker/{}".format(dataset.dataset_id)}})
        d.addCallback(created)
        return d

    def test_unknown_get(self):
        """
        ``/VolumeDriver.Get`` returns an error when asked for the mount path
        of a non-existent volume.
        """
        name = u"myvol"
        return self.assertResult(
            b"POST", b"/VolumeDriver.Get",
            {u"Name": name}, OK,
            {u"Err": u"Could not find volume with given name."})

    def test_non_local_get(self):
        """
        ``/VolumeDriver.Get`` returns an empty mount point when asked about a
        volume that is not mounted locally.
        """
        name = u"myvol"
        dataset_id = uuid4()

        # Create dataset on node B:
        d = self.flocker_client.create_dataset(
            self.NODE_B, int(DEFAULT_SIZE.to_Byte()),
            metadata={NAME_FIELD: name},
            dataset_id=dataset_id)
        d.addCallback(lambda _: self.flocker_client.synchronize_state())

        # Ask for path on node A:
        d.addCallback(lambda _:
                      self.assertResult(
                          b"POST", b"/VolumeDriver.Get",
                          {u"Name": name}, OK,
                          {u"Err": u"",
                           u"Volume": {
                               u"Name": name,
                               u"Mountpoint": u""}}))
        return d

    def test_list(self):
        """
        ``/VolumeDriver.List`` returns the mount path of the given volume if
        it is currently known and an empty mount point for non-local
        volumes.
        """
        name = u"myvol"
        remote_name = u"myvol3"

        d = gatherResults([
            self.flocker_client.create_dataset(
                self.NODE_A, int(DEFAULT_SIZE.to_Byte()),
                metadata={NAME_FIELD: name}),
            self.flocker_client.create_dataset(
                self.NODE_B, int(DEFAULT_SIZE.to_Byte()),
                metadata={NAME_FIELD: remote_name})])

        # The datasets arrive as state:
        d.addCallback(lambda _: self.flocker_client.synchronize_state())
        d.addCallback(lambda _:
                      self.flocker_client.list_datasets_configuration())
        d.addCallback(lambda datasets_config:
                      self.assertResult(
                          b"POST", b"/VolumeDriver.List",
                          {}, OK,
                          {u"Err": u"",
                           u"Volumes": sorted([
                               {u"Name": name,
                                u"Mountpoint": u"/flocker/{}".format(
                                    [key for (key, value)
                                     in datasets_config.datasets.items()
                                     if value.metadata["name"] == name][0])},
                               {u"Name": remote_name,
                                u"Mountpoint": u""},
                           ])}))
        return d

    def test_list_no_metadata_name(self):
        """
        ``/VolumeDriver.List`` omits volumes that don't have a metadata field
        for their name.
        """
        d = self.flocker_client.create_dataset(self.NODE_A,
                                               int(DEFAULT_SIZE.to_Byte()),
                                               metadata={})
        d.addCallback(lambda _:
                      self.assertResult(
                          b"POST", b"/VolumeDriver.List",
                          {}, OK,
                          {u"Err": u"",
                           u"Volumes": []}))
        return d


def _build_app(test):
    test.initialize()
    return VolumePlugin(
        test.volume_plugin_reactor, test.flocker_client, test.NODE_A).app
RealTestsAPI = build_UNIX_integration_tests(APITestsMixin, "API", _build_app)
