=====================
Using the API with Go
=====================

#. Download the :file:`example.go` file:

   :download:`example.go`

   .. literalinclude:: example.go

#. Before you run the example, you will need to change the following values (either by editing the source file or by setting environment variables):

   * **CONTROL_SERVICE** - the IP address of the Flocker control service
   * **CONTROL_PORT** - the port the control service is listening on
   * **KEY_FILE** - the API key file to use
   * **CERT_FILE** - the API certificate file to use
   * **CA_FILE** - the certificate authority file to use

#. Now you can run the example:

   .. prompt:: bash

	  go build example.go
	  ./example
