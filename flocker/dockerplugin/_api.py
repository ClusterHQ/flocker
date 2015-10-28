# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
An HTTP API implementing the Docker Volumes Plugin API.

See https://github.com/docker/docker/tree/master/docs/extend for details.
"""

from functools import wraps
from uuid import UUID

import yaml

from bitmath import GiB

from twisted.python.filepath import FilePath
from twisted.internet.task import deferLater

from klein import Klein

from ..restapi import structured
from ..control._config import dataset_id_from_name
from ..apiclient import DatasetAlreadyExists


SCHEMA_BASE = FilePath(__file__).sibling(b'schema')
SCHEMAS = {
    b'/types.json': yaml.safe_load(
        SCHEMA_BASE.child(b'types.yml').getContent()),
    b'/endpoints.json': yaml.safe_load(
        SCHEMA_BASE.child(b'endpoints.yml').getContent()),
    }


# The default size of a created volume. Pick a number that isn't the same
# as devicemapper loopback size (100GiB) so we don't trigger
# https://clusterhq.atlassian.net/browse/FLOC-2889 and that is large
# enough to hit Rackspace minimums. This is, obviously, not ideal.
DEFAULT_SIZE = int(GiB(75).to_Byte().value)


def _endpoint(name, ignore_body=False):
    """
    Decorator factory for API endpoints, adding appropriate JSON in/out
    encoding.

    :param unicode name: The name of the endpoint in the schema.
    :param ignore_body: If true, ignore the contents of the body for all
        HTTP methods, including ``POST``. By default the body is only
        ignored for ``GET`` and ``HEAD``.

    :return: Decorator for a method.
    """
    def decorator(f):
        @wraps(f)
        @structured(
            inputSchema={},
            outputSchema={u"$ref": u"/endpoints.json#/definitions/" + name},
            schema_store=SCHEMAS,
            ignore_body=ignore_body)
        def wrapped(*args, **kwargs):
            return f(*args, **kwargs)
        return wrapped
    return decorator


class VolumePlugin(object):
    """
    An implementation of the Docker Volumes Plugin API.

    We don't validate inputs with a schema since this is pre-existing code
    maintained by someone else, and lacking a schema provided by Docker we
    can't be sure they won't change things in minor ways. We do validate
    outputs to ensure we output the documented requirements.
    """
    _POLL_INTERVAL = 0.05

    app = Klein()

    def __init__(self, reactor, flocker_client, node_id):
        """
        :param IReactorTime reactor: Reactor time interface implementation.
        :param IFlockerAPIV1Client flocker_client: Client that allows
            communication with Flocker.
        :param UUID node_id: The identity of the local node this plugin is
            running on.
        """
        self._reactor = reactor
        self._flocker_client = flocker_client
        self._node_id = node_id

    @app.route("/Plugin.Activate", methods=["POST"])
    @_endpoint(u"PluginActivate", ignore_body=True)
    def plugin_activate(self):
        """
        Return which Docker plugin APIs this object supports.
        """
        return {u"Implements": [u"VolumeDriver"]}

    @app.route("/VolumeDriver.Remove", methods=["POST"])
    @_endpoint(u"Remove")
    def volumedriver_remove(self, Name):
        """
        Remove a Docker volume.

        :param unicode Name: The name of the volume.

        In practice we don't actually delete anything. As a multi-node
        volume driver we want to keep volumes around beyond lifetime of a
        specific container, or even a single node, so we don't delete
        datasets based on information from Docker.

        :return: Result indicating success.
        """
        return {u"Err": None}

    @app.route("/VolumeDriver.Unmount", methods=["POST"])
    @_endpoint(u"Unmount")
    def volumedriver_unmount(self, Name):
        """
        The Docker container is no longer using the given volume.

        :param unicode Name: The name of the volume.

        For now this does nothing. In FLOC-2755 this will release the
        lease acquired for the dataset by the ``VolumeDriver.Mount``
        handler.

        :return: Result indicating success.
        """
        return {u"Err": None}

    @app.route("/VolumeDriver.Create", methods=["POST"])
    @_endpoint(u"Create")
    def volumedriver_create(self, Name, Opts=None):
        """
        Create a volume with the given name.

        We hash the name to give a consistent dataset. This ensures that
        if due to race condition we attempt to create two volumes with
        same name only one will be created.

        We also check for existence of matching dataset based on
        ``"name"`` field in metadata, in case we're talking to cluster
        that has datasets that weren't created with this hashing
        mechanism.

        If there is a duplicate we don't return an error, but rather
        success: we will likely get unneeded creates from Docker since it
        doesn't necessarily know about existing persistent volumes.

        :param unicode Name: The name of the volume.

        :param dict Opts: Options passed from Docker for the volume
            at creation. ``None`` if not supplied in the request body.
            Currently ignored. ``Opts`` is a parameter introduced in the
            v2 plugins API introduced in Docker 1.9, it is not supplied
            in earlier Docker versions.

        :return: Result indicating success.
        """
        listing = self._flocker_client.list_datasets_configuration()

        def got_configured(configured):
            for dataset in configured:
                if dataset.metadata.get(u"name") == Name:
                    raise DatasetAlreadyExists
        listing.addCallback(got_configured)

        creating = listing.addCallback(
            lambda _: self._flocker_client.create_dataset(
                self._node_id, DEFAULT_SIZE, metadata={u"name": Name},
                dataset_id=UUID(dataset_id_from_name(Name))))
        creating.addErrback(lambda reason: reason.trap(DatasetAlreadyExists))
        creating.addCallback(lambda _: {u"Err": None})
        return creating

    def _get_path(self, name):
        """
        Return a volume's path if available.

        :param unicode name: The name of the volume.

        :return: ``Deferred`` that fires with the mountpoint ``FilePath``,
            or ``None`` if it is currently unknown.
        """
        # If we ever get rid of dataset_id hashing hack we'll need to
        # lookup the dataset by its metadata, not its id.
        dataset_id = UUID(dataset_id_from_name(name))
        d = self._flocker_client.list_datasets_state()

        def got_state(datasets):
            datasets = [dataset for dataset in datasets
                        if dataset.dataset_id == dataset_id]
            if datasets and datasets[0].primary == self._node_id:
                return datasets[0].path
            else:
                return None
        d.addCallback(got_state)
        return d

    @app.route("/VolumeDriver.Mount", methods=["POST"])
    @_endpoint(u"Mount")
    def volumedriver_mount(self, Name):
        """
        Move a volume with the given name to the current node and mount it.

        Since we need to return the filesystem path we wait until the
        dataset is mounted locally.

        :param unicode Name: The name of the volume.

        :return: Result that includes the mountpoint.
        """
        dataset_id = UUID(dataset_id_from_name(Name))
        d = self._flocker_client.move_dataset(self._node_id, dataset_id)

        def get_state(_=None):
            getting_path = self._get_path(Name)

            def got_path(path):
                if path is None:
                    return deferLater(
                        self._reactor, self._POLL_INTERVAL, get_state)
                else:
                    return {u"Err": None,
                            u"Mountpoint": path.path}
            getting_path.addCallback(got_path)
            return getting_path
        d.addCallback(get_state)
        return d

    @app.route("/VolumeDriver.Path", methods=["POST"])
    @_endpoint(u"Path")
    def volumedriver_path(self, Name):
        """
        Return the path of a locally mounted volume if possible.

        Docker will call this in situations where it's not clear to us
        whether the dataset should be local or not, so we can't wait for a
        result.

        :param unicode Name: The name of the volume.

        :return: Result indicating success.
        """
        d = self._get_path(Name)

        def got_path(path):
            if path is None:
                return {u"Err": u"Volume not available.",
                        u"Mountpoint": u""}
            else:
                return {u"Err": None,
                        u"Mountpoint": path.path}
        d.addCallback(got_path)
        return d
