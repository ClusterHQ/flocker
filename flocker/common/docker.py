# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Docker API client.
"""

from characteristic import attrs

from zope.interface import Interface, implementer

from docker import Client, APIError

from twisted.internet.defer import maybeDeferred


@attrs(["path", "mountpoint", "readonly"])
class VolumeMount(object):
    """
    Description of a volume mount within a container.

    :ivar FilePath path: Path on host filesystem.
    :ivar FilePath mountpoint: Path within container.
    :ivar bool readonly: Whether or not mount is read-only.
    """


class NotFound(Exception):
    """
    The referenced object was not found.
    """


class ServerError(Exception):
    """
    Internal error in the server.
    """


class IDockerClient(Interface):
    """
    A client that talks to the local Docker server.

    In general operations are asynchronous; results indicate that the
    docker daemon responded and started the operation, not that the action
    has finished.

    Results may errback with ``NotFound`` or ``ServerError`` as relevant.
    """

    def create_container(self, image, command=None, name=None, volumes=None):
        """
        Create a new container that can be started later.

        :param unicode image: The image to use.
        :param command: A ``list`` of bytes (the command to run) or
            ``None`` to use the default.
        :param name: If ``None`` a name is randomly generated, otherwise
            ``unicode`` should be given.
        :param volumes: ``None``, or a list of strings indicating mount
            points for volumes.

        :return: ``Deferred`` firing with a ``unicode`` container
            identifier when the operation is started by the Docker daemon.
        """

    def start_container(self, container, binds=None):
        """
        Start the given container.

        :param unicode container: The name or id of the container.
        :param binds: ``None``, or a list of ``VolumeMount`` instances
            matching the volumes defined when the container was created.

        :return: ``Deferred`` firing when the operation is started by the
            Docker daemon.
        """

    def remove_container(self, container):
        """
        Remove the given container.

        :param unicode container: The name or id of the container.

        :return: ``Deferred`` firing when the operation is started by the
            Docker daemon.
        """

    def inspect_container(self, container):
        """
        Return information about the given container.

        :param unicode container: The name or id of the container.

        :return: ``Deferred`` firing with a dictionary (decoded JSON
            result).
        """


@implementer(IDockerClient)
class DockerClient(object):
    """
    Talk to the real Docker server.

    For now we don't bother with any sort of asyncness since we're talking
    to localhost and expect answers back quickly. Longer term we may wish
    to adds threading, or perhaps write our own client.
    """
    def __init__(self):
        self._client = Client(version="1.10")

    def _extract_error(self, failure):
        failure.trap(APIError)
        code = failure.value.response.status_code
        if code == 404:
            raise NotFound()
        if code == 500:
            raise ServerError(failure.value.explanation)
        return failure

    def create_container(self, image, command=None, name=None, volumes=None):
        d = maybeDeferred(self._client.create_container, image, command=command,
                          name=name, volumes=volumes)
        d.addCallback(lambda result: result[u"Id"])
        d.addErrback(self._extract_error)
        return d

    def start_container(self, container, binds=None):
        if binds is not None:
            binds = {volume.path.path: {u"bind": volume.mountpoint.path,
                                        u"ro": volume.readonly}
                     for volume in binds}
        d = maybeDeferred(self._client.start, container, binds=binds)
        d.addErrback(self._extract_error)
        return d

    def remove_container(self, container):
        d = maybeDeferred(self._client.remove_container, container)
        d.addErrback(self._extract_error)
        return d

    def inspect_container(self, container):
        d = maybeDeferred(self._client.inspect_container, container)
        d.addErrback(self._extract_error)
        return d


@implementer(IDockerClient)
class FakeDockerClient(object):
    """
    Fake in-memory client.
    """
    def __init__(self):
        self._containers = {} # map id to some information

    def create_container(self, image, command=None, name=None, volumes=None):
        pass

    def start_container(self, container, binds=None):
        pass

    def remove_container(self, container):
        pass

    def inspect_container(self, container):
        pass
