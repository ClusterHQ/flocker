.. _configuration:

===================
Configuring Flocker
===================

Flocker operates on two configuration files: application and deployment.
Together these configurations define a deployment.

The configuration is represented using yaml syntax.

Application Configuration
-------------------------

The application configuration consists of a version and short, human-meaningful application names and the parameters necessary to run those applications.

The required parameters are ``version`` and ``applications``.
For now the ``version`` must be ``1``.

The parameters required to define an application are:

- ``image``

  This is the name of the Docker image which will be used to start the container which will run the application.
  Optionally, this may include a tag using the ``<name>:<tag>`` syntax.

  For example, an application which is meant to use version 1.0 of ClusterHQ's ``flocker-dev`` Docker image is configured like this:

  .. code-block:: yaml

     "image": "clusterhq/flocker-dev:v1.0"

The following parameters are optional when defining an application:

- ``ports``

  This is an optional list of port mappings to expose to the outside world.
  Connections to the *external* port on the host machine are forwarded to the *internal* port in the container.

  .. code-block:: yaml

     "ports":
     - "internal": 80
       "external": 8080

- ``volume``

  This specifies that the application container requires a volume.
  It also allows you to specify where in the container the volume will be mounted via the ``mountpoint`` key.
  The value for this key must be a string giving an absolute path.

  .. code-block:: yaml

     "volume":
       "mountpoint": "/var/www/data"

- ``environment``

  This is an optional mapping of key/value pairs for environment variables that will be applied to the application container.
  Keys and values for environment variables must be strings and only ASCII characters are supported at this time.

  .. code-block:: yaml

     "environment":
       "foo": "bar"
       "baz": "qux"

Here's an example of a simple but complete configuration defining one application:

.. code-block:: yaml

  "version": 1
  "applications":
    "site-clusterhq.com":
      "image": "clusterhq/clusterhq-website"
      "environment":
        "WP_ADMIN_USERNAME": "administrator"
        "WP_ADMIN_PASSWORD": "password"
      "ports":
      - "internal": 80
        "external": 8080
      "volume":
        "mountpoint": "/var/mysql/data"


Deployment Configuration
------------------------

The deployment configuration specifies which applications are run on what nodes.
It consists of a version and a mapping from node names to application names.

The required parameters are ``version`` and ``applications``.
For now the ``version`` must be ``1``.

Here's an example of a simple but complete configuration defining a deployment of one application on one host:

.. code-block:: yaml

  "version": 1
  "nodes":
    "node017.example.com":
      "site-clusterhq.com"
