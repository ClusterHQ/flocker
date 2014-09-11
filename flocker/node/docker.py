# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Docker API client.
"""

from __future__ import absolute_import

from zope.interface import implementer

from docker import Client
from docker.errors import APIError

from twisted.internet.threads import deferToThread

from .gear import IGearClient, AlreadyExists, Unit


# We namespace containers we manage so we don't clobber containers managed
# by others:
CONTAINER_NAMESPACE = u"flocker--"


@implementer(IGearClient)
class DockerClient(object):
    """
    Talk to the real Docker server directly.

    Some operations can take a while (e.g. stopping a container), so we
    use a thread pool.
    """
    def __init__(self):
        self._client = Client(version="1.12")

    def _to_container_name(self, unit_name):
        """
        Add the namespace to the container name.

        :param unicode unit_name: The unit's name.

        :return unicode: The container's name.
        """
        return CONTAINER_NAMESPACE + unit_name

    def add(self, unit_name, image_name, ports=None, links=None,
            environment=None):
        container_name = self._to_container_name(unit_name)
        def _add():
            self._client.create_container(image_name,
                                          name=container_name)
            self._client.start(container_name)
        d = deferToThread(_add)

        def _extract_error(failure):
            failure.trap(APIError)
            code = failure.value.response.status_code
            if code == 409:
                raise AlreadyExists(unit_name)
            return failure
        d.addErrback(_extract_error)
        return d

    def exists(self, unit_name):
        # XXX inefficient!
        d = self.list()

        def got_units(units):
            return unit_name in [unit.name for unit in units]
        d.addCallback(got_units)
        return d

    def remove(self, unit_name):
        container_name = self._to_container_name(unit_name)
        def _remove():
            try:
                self._client.stop(container_name)
                self._client.remove_container(container_name)
            except APIError as e:
                if e.response.status_code == 404:
                    return
                raise
        d = deferToThread(_remove)
        return d

    def list(self):
        def _list():
            result = set()
            ids = [d[u"Id"] for d in
                   self._client.containers(quiet=True, all=True)]
            for i in ids:
                data = self._client.inspect_container(i)
                state = u"active" if data[u"State"][u"Running"] else u"inactive"
                name = data[u"Name"]
                if not name.startswith(u"/" + CONTAINER_NAMESPACE):
                    continue
                else:
                    name = name[1 + len(CONTAINER_NAMESPACE):]
                result.add(Unit(name=name,
                                activation_state=state,
                                sub_state=u"",
                                # We'll add this and the other available
                                # info later, for now we're just aiming at
                                # GearClient compatibility.
                                container_image=None,
                            ))
            return result
        return deferToThread(_list)
