# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Docker API client.
"""

from __future__ import absolute_import

from zope.interface import implementer

from docker import Client
from docker.errors import APIError

from twisted.internet.threads import deferToThread

from .gear import IDockerClient, AlreadyExists, Unit


@implementer(IDockerClient)
class DockerClient(object):
    """
    Talk to the real Docker server directly.

    Some operations can take a while (e.g. stopping a container), so we
    use a thread pool.

    :ivar unicode namespace: A namespace prefix to add to container names
        so we don't clobber other applications interacting with Docker.
    """
    def __init__(self, namespace=u"flocker--"):
        self.namespace = namespace
        self._client = Client(version="1.12")

    def _to_container_name(self, unit_name):
        """
        Add the namespace to the container name.

        :param unicode unit_name: The unit's name.

        :return unicode: The container's name.
        """
        return self.namespace + unit_name

    def add(self, unit_name, image_name, ports=None, links=None,
            environment=None):
        container_name = self._to_container_name(unit_name)
        if environment is not None:
            environment = dict(environment.variables)
        if ports is None:
            ports = []

        def _create():
            self._client.create_container(
                image_name,
                name=container_name,
                environment=environment,
                ports=[p.internal_port for p in ports])

        def _add():
            try:
                _create()
            except APIError as e:
                if e.response.status_code == 404:
                    # Image was not found, so we need to pull it first:
                    self._client.pull(image_name)
                    _create()
                else:
                    raise
            self._client.start(container_name,
                               port_bindings={p.internal_port: p.external_port
                                              for p in ports})
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
                # Can't figure out how to get test coverage for this, but
                # it's definitely necessary:
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
                state = (u"active" if data[u"State"][u"Running"]
                         else u"inactive")
                name = data[u"Name"]
                if not name.startswith(u"/" + self.namespace):
                    continue
                else:
                    name = name[1 + len(self.namespace):]
                result.add(Unit(name=name,
                                activation_state=state,
                                sub_state=None,
                                # We'll add this and the other available
                                # info later, for now we're just aiming at
                                # GearClient compatibility.
                                container_image=None))
            return result
        return deferToThread(_list)
