.. _benchmarking:

Benchmarking
============

Flocker includes a tool for benchmarking operations.
It needs the appropriate ssh-key added to a running ssh-agent.
It is called like this:

.. prompt:: bash $

   python benchmark/benchmark_control.py <options>


The :program:`benchmark/benchmark_control.py` script has several options:

.. program:: benchmark/benchmark_control.py

.. option:: --control <control-service-ipaddr>

   Specifies the IP address for the Flocker cluster control node.
   Defaults to using a fake control service for testing.

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

      ``nop``
         A no-op operation.

      ``read-request``
         Read from the control service.
         This is the default.

.. option:: --measure <measurement>

   Specifies the quantity to measure while the operation is performed.
   Supported values include:

      ``wallclock``
         Actual clock time elapsed.
         This is the default.

To see the supported values for each option, run:

.. prompt:: bash $

   python benchmark/benchmark_control.py --help
