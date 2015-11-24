.. _benchmarking:

Benchmarking
============

Flocker includes a tool for benchmarking operations.
It is called like this:

.. prompt:: bash $

   benchmark/benchmark <options>


The :program:`benchmark` script has several options:

.. program:: benchmark

.. option:: --control <control-service-ipaddr>

   Specifies the IP address for the Flocker cluster control node.
   This must be specified, unless the ``no-op`` operation is requested.

.. option:: --certs <directory>

   Specifies the directory containing the user certificates.
   Defaults to the directory ``./certs``.

.. option:: --scenario <scenario>

   Specifies the scenario to run the benchmark under.
   Supported values include:

      ``no-load``
         No additional load on system.
         This is the default.

.. option:: --operation <operation>

   Specifies the operation to be benchmarked.
   This operation is sampled 3 times.
   Supported values include:

      ``no-op``
         A no-op operation that performs no action.

      ``read-request``
         Read from the control service.
         This is the default.

      ``wait-10``
         Wait 10 seconds between measurements.

.. option:: --metric <metric>

   Specifies the quantity to measure while the operation is performed.
   Supported values include:

      ``wallclock``
         Actual clock time elapsed.
         This is the default.

To see the supported values for each option, run:

.. prompt:: bash $

   benchmark/benchmark --help
