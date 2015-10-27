========================
Deployment Configuration
========================

The deployment configuration specifies which applications are run on what nodes.
It consists of a version and a mapping from node IPv4 addresses to application names.

The required parameters are ``version`` and ``nodes``.
For now the ``version`` must be ``1``.

Each entry under ``nodes`` should be a mapping of the desired deployment node's IP address to a list of application names that match those defined in the application configuration.

Here's an example of a simple but complete configuration defining a deployment of one application on one host:

.. code-block:: yaml

  "version": 1
  "nodes":
    "203.0.113.100":
      - "site-clusterhq.com"
      - "postgresql"
