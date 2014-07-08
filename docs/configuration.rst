=============
Configuration
=============

Flocker operates on two configuration files: application and deployment.
Together these configurations define a deployment.

The configuration is represented using yaml syntax.

Application Configuration
-------------------------

The application configuration consists of short, human-meaningful application names and the parameters necessary to run those applications.

The parameters required to define an application are:

  - ``image``

    This is the name of the Docker image which will be used to start the container which will run the application.
    Optionally, this may include a tag using the ``<name>:<tag>`` syntax.

    For example, an application which is meant to use version 1.0 of ClusterHQ's flocker-dev Docker image is configured like this::

       image: clusterhq/flocker-dev:v1.0

Here's an example of a simple but complete configuration defining one application:

.. code-block:: yaml

   "site-clusterhq.com":
       "image": "clusterhq/clusterhq-website"


Deployment Configuration
------------------------

The deployment configuration specifies which applications are run on what nodes.
It consists of a mapping from node names to application names.

Here's an example of a simple but complete configuration defining a deployment of one application on one host:

.. code-block:: yaml

  "node017.clusterhq.internal":
      - "site-clusterhq.com"
