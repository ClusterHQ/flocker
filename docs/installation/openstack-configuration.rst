.. _openstack-dataset-backend:

============================================
OpenStack Block Device Backend Configuration
============================================

The OpenStack backend uses Cinder volumes as the storage for datasets.
This backend can be used with Flocker dataset agent nodes run by OpenStack Nova.
The configuration item to use OpenStack should look like:

.. code-block:: yaml

   dataset:
       backend: "openstack"
       region: "<region slug; for example, LON>"
       auth_plugin: "<authentication plugin>"
       ...

Make sure that the ``region`` specified matches the region where the Flocker nodes run.
OpenStack must be able to attach volumes created in that region to your Flocker agent nodes.

.. note::
	For the Flocker OpenStack integration to be able to identify the virtual machines where you run the Flocker agents, and to attach volumes to them, those virtual machines **must be provisioned through OpenStack** (via Nova).

.. XXX FLOC-2091 - Fix up this section.

If the OpenStack cloud uses certificates that are issued by a private Certificate Authority (CA), add the field ``verify_ca_path`` to the dataset stanza, with the path to the CA certificate.

.. code-block:: yaml

   dataset:
       backend: "openstack"
       region: "DFW"
       verify_ca_path: "/etc/flocker/openstack-ca.crt"
       auth_plugin: "password"
       ...

For testing purposes, it is possible to turn off certificate verification, by setting the ``verify_peer`` field to ``false``.

.. warning::

   Only use this insecure setting for troubleshooting, as it is does not check that the remote server's credential is valid.

.. code-block:: yaml

   dataset:
       backend: "openstack"
       region: "DFW"
       verify_peer: false
       auth_plugin: "password"
       ...

Other items are typically required but vary depending on the `OpenStack authentication plugin selected`_
(Flocker relies on these plugins; it does not provide them itself).

Flocker does provide explicit support for a ``rackspace`` authentication plugin.
This plugin requires ``username``, ``api_key``, and ``auth_url``.

For example:

.. code-block:: yaml

   dataset:
       backend: "openstack"
       region: "<region slug; for example, LON>"
       auth_plugin: "rackspace"
       username: "<your rackspace username>"
       api_key: "<your rackspace API key>"
       auth_url: "https://identity.api.rackspacecloud.com/v2.0"

To find the requirements for other plugins, see the appropriate documentation in the OpenStack project or provided with the plugin.

.. _OpenStack authentication plugin selected: http://docs.openstack.org/developer/python-keystoneclient/authentication-plugins.html#loading-plugins-by-name
