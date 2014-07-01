# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.node.test.test_application -*-

"""
An API for creating application containers.

laptop$ cat app.cfg
{"version": 1,
 "mysql-hybridcluster": {"image": "hybridlogic/mysql5.9", "volume": "/var/run/mysql"},
 "site-hybridcluster.com": {
    "image": "hybridlogic/web",
    "volume": "/var/log",
    "internal_links": {3306: {"container": "mysql-hybridcluster", "port": 3306}},
    "external_links": {"external": 80, "internal": 80},
 }
}

laptop$ flocker-cli go deploy.cfg app.cfg

  # ssh node1 flocker-node inspect-local-state
  #   {}
  # ssh node2 flocker-node inspect-local-state
  #   {}

  # CURRENT_CONFIG={"node1": {}, "node2": {}}
  # DEPLOY_CFG=$(cat deploy.cfg)
  # APP_CFG=$(cat app.cfg)
  # ssh node1 flocker-node change-local-state "${CURRENT_CONFIG}" "${DEPLOY_CFG}" "${APP_CFG}"

    // Create a new docker container using gear and the supplied config
    # gear install hybridlogic/mysql5.9 mysql-hybridcluster

    // Create a new flocker volume for that container to use
    # flocker-volume create mysql-hybridcluster

    // Forward the website container's external port to the other node where
    // the config told us the website is running.  This lets end-users connect
    // to any node in the cluster and get the right thing.
    # iptables ${forward node1 port 80 to node2 port 80}

    // Boot the container
    # gear start mysql-hybridcluster

    // gear and docker are not very reliable.  poll the system somehow until
    // you see things are working.
    # check to make sure it worked!@
"""

class Application(object):
    """
    :ivar unicode name: A unique name for this application.
    :ivar unicode image: The `Docker` image containing the application.
    :ivar unicode volume_mount_path: The path at which to mount a flocker
        volume within the application.
    :ivar list internal_links: A list of mappings between internal ports and
        the external port of another application.
    :ivar external_links: A list of mappings between a port exposed by the
        container and a port on the host.
    """
    
    @classmethod
    def create(cls, name, image, volume_mount_path, internal_links, external_links):
        """
        Create a unit with the given name, based on the given image and with
        the internal and external port mappings.
        
        :raises ApplicationExists: if an application with that name already exists.
        :raises UnknownImage: if the supplied image is not a known Docker image.
        """

    @classmethod
    def from_config(cls, config):
        """
        XXX: This will require access to the full application configuration
        object. So maybe we need to start by creating that configuration
        object.
        """


class ApplicationConfiguration(object):
    def from_yaml(self, yaml_file):
        """
        :param FilePath yaml_file: A Yaml file to be parsed.

        :raises UnknownApplication: if the supplied internal_links contains a
            reference to an application name that is now known.
        """
        # Do yaml parsing of file.
        # Check for duplicate external ports.
        # Check internal_links for references to unknown application names.
        # Check internal_links for references to un-exposed ports on other applications.
        # Create `Application` objects for each application.

def deploy():
    """
    
    """
    
