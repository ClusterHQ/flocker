.. _benchmarking:

Benchmarking
============

.. note::

   For the ``benchmark`` command described on this page, if the cluster uses private addresses for communication (e.g. AWS nodes), set the environment variable ``FLOCKER_ACCEPTANCE_HOSTNAME_TO_PUBLIC_ADDRESS`` to a serialized JSON object mapping cluster internal IP addresses to public IP addresses.
   This environment variable is provided if the cluster is started using the ``run-acceptance-tests`` command.
   This is intended to be a temporary requirement, until other mechanisms are available [:issue:`2137`, :issue:`3514`, :issue:`3521`].

Flocker includes a tool for benchmarking operations.
It is called like this:

.. prompt:: bash $

   benchmark/benchmark <options>

The :program:`benchmark` script has the following command line options:

.. program:: benchmark

.. option:: --control <control-service-ipaddr>

   Specifies the IP address for the Flocker cluster control node.
   This must be specified, unless the ``no-op`` operation is requested.

.. option:: --certs <directory>

   Specifies the directory containing the user certificates.
   Defaults to the directory ``./certs``.

.. option:: --config <config-file>

   Specifies a file containing configurations for scenarios, operations, and metrics.
   See below for the format of this file.
   Defaults to the file ``./benchmark.yml``.

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


Configuration File
------------------

The :program:`benchmark` script requires a configuration file describing the possible scenarios, operations, and metrics.
Each of these has a name, a type, and possibly other parameters.

An example file:

.. code-block:: yaml

   scenarios:
     - name: default
       type: no-load

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

Operation Types
~~~~~~~~~~~~~~~

.. option:: no-op

   A no-op operation that performs no action.

.. option:: read-request

   Read the current cluster state from the control service.

.. option:: wait

   Wait for a number of seconds between measurements.
   The number of seconds to wait must be provided as an additional ``wait_seconds`` property.

Metric Types
~~~~~~~~~~~~

.. option:: cputime

   CPU time elapsed.

.. option:: wallclock

   Actual clock time elapsed.
