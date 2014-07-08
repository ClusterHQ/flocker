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


@attributes(["name", "image"], defaults=dict(image=None))
class Application(object):
    """
    A single `application <http://12factor.net/>`_ to be deployed.

    XXX: The image attribute defaults to `None` until we have a way to
    interrogate geard for the docker images associated with its containers. See
    https://github.com/ClusterHQ/flocker/issues/207

    :ivar unicode name: A short, human-readable identifier for this
        application.  For example, ``u"site-example.com"`` or
        ``u"pgsql-payroll"``.

    :ivar DockerImage image: An image that can be used to run this
        containerized application.
    """
