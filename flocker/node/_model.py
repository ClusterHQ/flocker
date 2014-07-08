# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_model -*-

"""
Record types for representing deployment models.
"""

from characteristic import attributes


@attributes(["repository", "tag"], defaults=dict(tag=u'latest'))
class DockerImage(object):
    """
    An image that can be used to run an application using Docker.

    :ivar unicode repository: eg ``u"hybridcluster/flocker"``
    :ivar unicode tag: eg ``u"release-14.0"``
    :ivar unicode full_name: A readonly property which combines the repository
        and tag in a format that can be passed to `docker run`.
    """
    @property
    def full_name(self):
        return "{repository}:{tag}".format(
            repository=self.repository, tag=self.tag)

    @classmethod
    def from_string(cls, input):
        kwargs = {}
        parts = input.rsplit(':', 1)
        repository = parts[0]
        if not repository:
            raise ValueError("Docker image names must have format 'repository[:tag]'. Found '{image_name}'".format(image_name=input))
        kwargs['repository'] = repository
        if len(parts) == 2:
            kwargs['tag'] = parts[1]
        return cls(**kwargs)


@attributes(["name", "image"])
class Application(object):
    """
    A single `application <http://12factor.net/>`_ to be deployed.

    :ivar unicode name: A short, human-readable identifier for this
        application.  For example, ``u"site-example.com"`` or
        ``u"pgsql-payroll"``.

    :ivar DockerImage image: An image that can be used to run this
        containerized application.
    """

@attributes(["hostname", "applications"])
class Node(object):
    """
    A single node on which applications will be managed (deployed,
    reconfigured, destroyed, etc).

    :ivar unicode hostname: The hostname of the node.  This must be a
        resolveable name so that Flocker can connect to the node.  This may be
        a literal IP address instead of a proper hostname.

    :ivar set applications: A ``set`` of ``Application`` instances describing
        the applications which are to run on this ``Node``.
    """
