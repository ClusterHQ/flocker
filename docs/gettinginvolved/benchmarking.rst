.. _benchmarking:

Benchmarking
============

Flocker includes a tool for benchmarking operations.
It is called like this:

.. prompt:: bash $

   benchmark/benchmark <options>

The :program:`benchmark` script has the following command line options:

.. program:: benchmark

.. option:: --cluster <cluster-config>

   Specifies a directory containing:

   - ``cluster.yml`` - a cluster description file;
   - ``cluster.crt`` - a CA certificate file;
   - ``user.crt`` - a user certificate file; and
   - ``user.key`` - a user private key file.

   These files are equivalent to those created by the :ref:`Quick Start Flocker Installer <labs-installer>`.
   The format of the :file:`cluster.yml` file is specified in the  :ref:`benchmarking-cluster-description` section below.

   If this option is not specified, then the benchmark script expects environment variables as set by the :ref:`acceptance test runner <acceptance-testing-cluster-config>` using ```run-acceptance-tests --keep``.

.. option:: --config <benchmark-config>

   Specifies a file containing configurations for scenarios, operations, and metrics.
   The format of this file is specified in the :ref:`benchmarking-configuration-file` section below.
   Defaults to the file ``./benchmark.yml``.

.. option:: --samples <integer>

   Specifies the number of times to run the benchmark measurements.
   Defaults to 3.

.. option:: --scenario <scenario>

   Specifies the scenario to run the benchmark under.
   This is the ``name`` of a scenario in the configuration file.
   Defaults to the name ``default``.

.. option:: --operation <operation>

   Specifies the operation to be benchmarked.
   This is the ``name`` of an operation in the configuration file.
   Defaults to the name ``default``.
   The operation is sampled 3 times.

.. option:: --metric <metric>

   Specifies the quantity to measure while the operation is performed.
   This is the ``name`` of a metric in the configuration file.
   Defaults to the name ``default``.

.. option:: --userdata <json-data>

   Specifies JSON data to be added to the result JSON.
   If the value starts with ``@`` the remainder of the value is the name of a file containing JSON data.
   Otherwise, the value must be a valid JSON structure.
   The supplied data is added as the ``userdata`` property of the output result.


.. _benchmarking-cluster-description:

Cluster Description File
------------------------

This file must be named :file:`cluster.yml` and must be located in the directory named by the ``--cluster`` option.

An example file:

.. code-block:: yaml

   agent_nodes:
    - {public: 172.31.105.15, private: 10.0.84.25}
    - {public: 172.31.105.16, private: 10.0.84.22}
   control_node: 172.31.105.15

.. _benchmarking-configuration-file:

Configuration File
------------------

The :program:`benchmark` script requires a configuration file describing the possible scenarios, operations, and metrics.
Each of these has a name, a type, and possibly other parameters.

An example file:

.. code-block:: yaml

   scenarios:
     - name: default
       type: no-load

     - name: read-request-5
       type: read-request-load
       request_rate: 5

     - name: read-request-10
       type: read-request-load
       request_rate: 10
       sample_size: 10
       timeout: 60

   operations:
     - name: default
       type: read-request

     - name: wait-10
       type: wait
       wait_seconds: 10

     - name: wait-100
       type: wait
       wait_seconds: 100

   metrics:
     - name: default
       type: wallclock

     - name: cputime
       type: cputime

Scenario Types
~~~~~~~~~~~~~~

.. option:: no-load

   No additional load on system.

.. option:: read-request-load

   Create additional load on the system by performing read requests.

   Specify the operation to be performed using an additional ``method`` property.
   The value must be the name of a zero-parameter method in the ``flocker.apiclient.IFlockerAPIV1Client`` interface, and defaults to ``version``.

   Specify the rate of requests to perform per second using an additional ``request_rate`` property.
   The default is 10 requests per second.

   Specify the number of samples to be collected when sampling the request rate using an additional ``sample_size`` property.
   The default is 5 samples.

   Specify a timeout for establishing the scenario using an additional ``timeout`` property.
   The default is 45 seconds.

.. option:: write-request-load

   Create additional load on the system by performing write requests, specifically a dataset move that has no real effect (target = source).

   Specify the rate of requests to perform per second using an additional ``request_rate`` property.
   The default is 10 requests per second.

   Specify the number of samples to be collected when sampling the request rate using an additional ``sample_size`` property.
   The default is 5 samples.

   Specify a timeout for establishing the scenario using an additional ``timeout`` property.
   The default is 45 seconds.


Operation Types
~~~~~~~~~~~~~~~

.. option:: create-container

   Create a stateful container and wait for it to be running.

   Specify the container image using an additional ``image`` property.
   The container will be started with the default command line.
   Hence the image must have a long-lived default command line.
   The default image is ``clusterhq/mongodb``.

   Specify the size of the dataset using an additional ``volume_size`` property.
   If specifying a cluster using environment variables, this defaults to the value of the ``FLOCKER_ACCEPTANCE_DEFAULT_VOLUME_SIZE`` environment variable.
   Otherwise, it defaults to a platform-specific value.

   Specify the volume mountpoint using an additional ``mountpoint`` property.
   The default is ``/data``.

.. option:: create-dataset

   Create a dataset and wait for it to be mounted.

   Specify the size of the dataset using an additional ``volume_size`` property.
   If specifying a cluster using environment variables, this defaults to the value of the ``FLOCKER_ACCEPTANCE_DEFAULT_VOLUME_SIZE`` environment variable.
   Otherwise, it defaults to a platform-specific value.

.. option:: no-op

   A no-op operation that performs no action.

.. option:: read-request

   Perform a read operation on the control service.

   Specify the operation to be performed using an additional ``method`` property.
   The value must be the name of a zero-parameter method in the ``flocker.apiclient.IFlockerAPIV1Client`` interface, and defaults to ``version``.

.. option:: wait

   Wait for a number of seconds between measurements.

   Specify the number of seconds to wait using an additional ``wait_seconds`` property.
   The default is 10 seconds.

Metric Types
~~~~~~~~~~~~

.. option:: cputime

   CPU time elapsed.
   Specify the process names to be monitored using an additional ``processes`` property.
   The value must be a list of process name strings, and defaults to the names of the Flocker services.

.. option:: wallclock

   Actual clock time elapsed.
