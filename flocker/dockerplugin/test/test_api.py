# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
Tests for the Volumes Plugin API provided by the plugin.
"""

from uuid import uuid4, UUID

from twisted.web.http import OK
from twisted.internet import reactor
from twisted.internet.task import Clock, deferLater
from twisted.python.components import proxyForInterface
from twisted.internet.interfaces import IReactorTime

from pyrsistent import pmap

from characteristic import attributes

from .._api import VolumePlugin, DEFAULT_SIZE
from ...apiclient import FakeFlockerClient, Dataset
from ...control._config import dataset_id_from_name
from ...node.agents.test.test_blockdevice import CountingProxy

from ...restapi.testtools import buildIntegrationTests, APIAssertionsMixin


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


@attributes(["clock", "reactor"])
class AutomaticClock(proxyForInterface(IReactorTime, "clock")):
    """
    This is an automatic clock, which schedules itself to advance whenever
    there is a pending call.

    :ivar Clock clock: The underlying clock that gets all calls proxied to it.
        This clock is advanced with every call to callLater.
    :ivar IReactorTime reactor: This ``IReactorTime`` provider is used to
        provide an alternate context to advance the clock from. It is not
        realistic to advance the clock from the context that calls
        ``callLater``, so we require a different context to advance this clock
        from.
    :ivar bool _scheduled: boolean indicating if the clock is currently
        scheduled to advance.
    """
    def __init__(self):
        self._scheduled = False
        pass

    def _advance(self):
        """
        Advance the underlying clock once up to the nearest pending delayed
        call. Then schedule the clock for another update.
        """
        self._scheduled = False
        delayed_calls = self.clock.getDelayedCalls()
        if delayed_calls:
            next_time = min(t.getTime() for t in delayed_calls)
            diff = next_time - self.clock.seconds()
            self.clock.advance(diff)
        self._schedule()

    def _schedule(self):
        """
        Schedule this clock to be advanced in a different context (provided by
        self.reactor). Only schedule if there are pending ``DelayedCalls``.
        """
        if not self._scheduled and self.clock.getDelayedCalls():
            self._scheduled = True
            self.reactor.callLater(0.0, self._advance)

    def callLater(self, when, what, *a, **kw):
        """
        Queue up the later call on the underlying ``Clock``, and then schedule
        this clock for advancement.
        """
        d = self.clock.callLater(when, what, *a, **kw)
        # It is not realistic to call self.clock.advance(when) in the current
        # context. In practice callLater _always_ schedules work on a different
        # context. Use a different ``IReactorTime`` provider to schedule the
        # advancement of this clock at a different time.
        self._schedule()
        return d


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
        self._clock = Clock()
        self.reactor = AutomaticClock(clock=self._clock, reactor=reactor)
        self.flocker_client = SimpleCountingProxy(FakeFlockerClient())

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
        # Node A. Attaching this to the _clock so that this does _not_ advance
        # time, but merely waits for other callLater calls to self.reactor to
        # advance the clock.
        self._clock.callLater(5.0, self.flocker_client.synchronize_state)

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
        dataset_id = UUID(dataset_id_from_name(name))
        # Create dataset on a different node:
        d = self.flocker_client.create_dataset(
            self.NODE_B, DEFAULT_SIZE, metadata={u"name": name},
            dataset_id=dataset_id)

        # Pretend that it takes 500 seconds for the dataset to get established
        # on Node A. This should be longer than our timeout.  Attaching this to
        # the _clock so that this does _not_ advance time, but merely waits for
        # other callLater calls to self.reactor to advance the clock.
        self._clock.callLater(500.0, self.flocker_client.synchronize_state)

        d.addCallback(lambda _:
                      self.assertResult(
                          b"POST", b"/VolumeDriver.Mount",
                          {u"Name": name}, OK,
                          {u"Err": u"Timed out waiting for dataset to mount.",
                           u"Mountpoint": u""}))
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
