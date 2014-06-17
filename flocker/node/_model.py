from characteristic import attributes

@attributes(["mount_path"])
class Volume(object):
    """
    A single filesystem volume to be associated with an application.

    :ivar FilePath mount_path: The absolute path at which the volume will be
        mounted onto the application image filesystem.
    """


@attributes(["repository", "tag"])
class DockerImage(object):
    """
    An image that can be used to run an application using Docker.

    :ivar unicode repository: eg ``u"hybridcluster/flocker"``
    :ivar unicode tag: eg ``u"release-14.0"``
    """


@attributes(["name", "image", "volume"])
class Application(object):
    """
    A single `application <http://12factor.net/>`_ to be deployed.

    :ivar unicode name: A short, human-readable identifier for this
        application.  For example, ``u"site-example.com"`` or
        ``u"pgsql-payroll"``.

    :ivar DockerImage image: An image that can be used to run this containerized
        application.

    :ivar Volume volume: A volume which will always be made available with this
        application.
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


@attributes(["nodes"])
class Deployment(object):
    """
    A ``Deployment`` describes the configuration of a number of applications on
    a number of cooperating nodes.  This might describe the real state of an
    existing deployment or be used to represent a desired future state.

    :ivar set nodes: A ``set`` containing ``Node`` instances describing the
        configuration of each cooperating node.
    """


