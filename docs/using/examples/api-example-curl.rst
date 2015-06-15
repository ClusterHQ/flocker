=======================
Using the API with cURL
=======================

.. note:: You will need to have a running Flocker cluster set up, and at least `Python 2.7.9`_ to run this example.

#. Download the :file:`example.py` file:

   :download:`example.py`

   .. literalinclude:: example.py

#. Before you run the example, you will need to change the following values (either by editing the source file or by setting environment variables):

   * **CONTROL_SERVICE** - the IP address of the Flocker control service
   * **CONTROL_PORT** - the port the control service is listening on
   * **KEY_FILE** - the API key file to use
   * **CERT_FILE** - the API certificate file to use
   * **CA_FILE** - the certificate authority file to use

#. Now you can run the example:

   .. prompt:: bash

      python example.py

.. _`Python 2.7.9`: https://www.python.org/downloads/
